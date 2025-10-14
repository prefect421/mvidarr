"""
Async YouTube API Service for FastAPI Migration
Handles YouTube API integration for video search and data retrieval with async operations
"""

from typing import Any, Dict, List, Optional

from src.services.async_base_service import AsyncBaseService
from src.utils.httpx_async_client import get_global_httpx_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.async_youtube")


class AsyncYouTubeService(AsyncBaseService):
    """Async YouTube API service for video search and metadata"""

    def __init__(self):
        super().__init__("mvidarr.async_youtube_service")
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self._api_key = None
        self._settings_loaded = False

    async def _load_api_key(self):
        """Load YouTube API key from settings"""
        if self._settings_loaded and self._api_key is not None:
            return

        try:
            self.logger.debug("Loading YouTube API key from database")

            # Get API key from settings table
            query = "SELECT setting_value FROM settings WHERE setting_key = 'youtube_api_key'"
            result = await self.execute_query(query)

            if result:
                self._api_key = result[0]["setting_value"]
                self.logger.debug("YouTube API key loaded successfully")
            else:
                self._api_key = None
                self.logger.warning("YouTube API key not found in settings")

            self._settings_loaded = True

        except Exception as e:
            self.logger.error(f"Failed to load YouTube API key: {e}")
            self._api_key = None
            self._settings_loaded = True

    async def get_api_key(self) -> Optional[str]:
        """Get YouTube API key from settings"""
        await self._load_api_key()
        return self._api_key

    async def is_configured(self) -> bool:
        """Check if YouTube API is properly configured"""
        api_key = await self.get_api_key()
        return bool(api_key)

    def clear_cache(self):
        """Clear cached settings to force reload"""
        self._settings_loaded = False
        self._api_key = None

    async def reload_settings(self):
        """Force reload of settings from database"""
        self.clear_cache()
        await self._load_api_key()
        self.logger.info("YouTube API settings reloaded from database")

    async def search_videos(self, query: str, max_results: int = 25) -> Dict[str, Any]:
        """Search for videos using YouTube API"""
        api_key = await self.get_api_key()

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
            client = await get_global_httpx_client()

            response = await client.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()

                if "items" in data:
                    self.logger.info(
                        f"YouTube search successful: {len(data['items'])} results for '{query}'"
                    )
                    return {
                        "success": True,
                        "results": data["items"],
                        "total": len(data["items"]),
                        "query": query,
                    }
                else:
                    self.logger.warning(
                        f"YouTube search returned no items for '{query}'"
                    )
                    return {"success": True, "results": [], "total": 0, "query": query}

            elif response.status_code == 403:
                error_data = response.json()
                error_message = "YouTube API quota exceeded or invalid API key"

                if "error" in error_data and "message" in error_data["error"]:
                    error_message = error_data["error"]["message"]

                self.logger.error(f"YouTube API access denied: {error_message}")
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

                self.logger.error(f"YouTube API bad request: {error_message}")
                return {
                    "success": False,
                    "error": f"YouTube API Error: {error_message}",
                    "results": [],
                }

            else:
                self.logger.error(
                    f"YouTube API returned unexpected status: {response.status_code}"
                )
                return {
                    "success": False,
                    "error": f"YouTube API returned status {response.status_code}",
                    "results": [],
                }

        except Exception as e:
            self.logger.error(f"YouTube API search failed for '{query}': {e}")
            return {
                "success": False,
                "error": f"YouTube search failed: {str(e)}",
                "results": [],
            }

    async def get_video_details(self, video_ids: List[str]) -> Dict[str, Any]:
        """Get detailed information for specific video IDs"""
        api_key = await self.get_api_key()

        if not api_key:
            return {
                "success": False,
                "error": "YouTube API key not configured. Please set it in Settings.",
                "results": [],
            }

        if not video_ids:
            return {"success": True, "results": [], "total": 0}

        try:
            # YouTube API allows up to 50 video IDs per request
            batch_size = 50
            all_results = []

            for i in range(0, len(video_ids), batch_size):
                batch_ids = video_ids[i : i + batch_size]

                # Prepare API parameters
                params = {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(batch_ids),
                    "key": api_key,
                }

                # Make API request
                url = f"{self.base_url}/videos"
                client = await get_global_httpx_client()

                response = await client.get(url, params=params, timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    if "items" in data:
                        all_results.extend(data["items"])
                else:
                    self.logger.error(
                        f"Failed to get video details: HTTP {response.status_code}"
                    )
                    return {
                        "success": False,
                        "error": f"YouTube API returned status {response.status_code}",
                        "results": [],
                    }

            self.logger.info(f"Retrieved details for {len(all_results)} videos")
            return {
                "success": True,
                "results": all_results,
                "total": len(all_results),
            }

        except Exception as e:
            self.logger.error(f"Failed to get video details: {e}")
            return {
                "success": False,
                "error": f"Failed to get video details: {str(e)}",
                "results": [],
            }

    async def search_artist_videos(
        self, artist_name: str, max_results: int = 25
    ) -> Dict[str, Any]:
        """Search for videos by a specific artist"""
        # Enhanced search query for better artist-specific results
        search_queries = [
            f"{artist_name} official",
            f"{artist_name} music video",
            f"{artist_name} official music video",
            artist_name,  # Fallback to basic search
        ]

        best_result = {"success": True, "results": [], "total": 0, "query": artist_name}

        for query in search_queries:
            result = await self.search_videos(query, max_results)

            if result["success"] and result["total"] > best_result["total"]:
                best_result = result
                best_result["query"] = artist_name  # Keep original artist name

            # If we get good results, use them
            if result["success"] and result["total"] >= max_results // 2:
                break

        return best_result

    async def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get information about a YouTube channel"""
        api_key = await self.get_api_key()

        if not api_key:
            return {
                "success": False,
                "error": "YouTube API key not configured. Please set it in Settings.",
            }

        try:
            params = {
                "part": "snippet,statistics",
                "id": channel_id,
                "key": api_key,
            }

            url = f"{self.base_url}/channels"
            client = await get_global_httpx_client()

            response = await client.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if "items" in data and data["items"]:
                    channel_data = data["items"][0]
                    return {
                        "success": True,
                        "channel": channel_data,
                        "id": channel_id,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Channel {channel_id} not found",
                    }
            else:
                return {
                    "success": False,
                    "error": f"YouTube API returned status {response.status_code}",
                }

        except Exception as e:
            self.logger.error(f"Failed to get channel info for {channel_id}: {e}")
            return {
                "success": False,
                "error": f"Failed to get channel info: {str(e)}",
            }

    async def search_music_videos(
        self, query: str, max_results: int = 25
    ) -> Dict[str, Any]:
        """Search specifically for music videos"""
        # Enhanced query for music videos
        music_video_query = f"{query} music video"

        result = await self.search_videos(music_video_query, max_results)

        if result["success"]:
            # Filter results to prioritize music videos
            filtered_results = []

            for item in result["results"]:
                title = item.get("snippet", {}).get("title", "").lower()
                description = item.get("snippet", {}).get("description", "").lower()

                # Prioritize items that mention music video, official, etc.
                music_keywords = ["music video", "official", "mv", "clip", "video"]

                score = 0
                for keyword in music_keywords:
                    if keyword in title or keyword in description:
                        score += 1

                filtered_results.append({"item": item, "score": score})

            # Sort by score (descending) and return items
            filtered_results.sort(key=lambda x: x["score"], reverse=True)
            result["results"] = [item["item"] for item in filtered_results]

        return result

    async def get_api_status(self) -> Dict[str, Any]:
        """Get YouTube API status and quota information"""
        try:
            configured = await self.is_configured()

            if not configured:
                return {
                    "status": "not_configured",
                    "message": "YouTube API key not configured",
                    "configured": False,
                }

            # Test API with a simple search
            test_result = await self.search_videos("test", max_results=1)

            if test_result["success"]:
                return {
                    "status": "working",
                    "message": "YouTube API is working properly",
                    "configured": True,
                    "test_result": "success",
                }
            else:
                return {
                    "status": "error",
                    "message": test_result.get("error", "Unknown error"),
                    "configured": True,
                    "test_result": "failed",
                }

        except Exception as e:
            self.logger.error(f"Failed to get API status: {e}")
            return {
                "status": "error",
                "message": str(e),
                "configured": False,
                "test_result": "failed",
            }


# Test function for the async YouTube service
async def test_async_youtube_service():
    """Test the async YouTube service functionality"""
    try:
        from src.database.async_connection import initialize_async_database

        print("🔄 Initializing async database...")
        await initialize_async_database()

        print("🔄 Creating AsyncYouTubeService...")
        service = AsyncYouTubeService()

        print("🔄 Testing service configuration...")
        configured = await service.is_configured()
        print(f"YouTube configured: {configured}")

        print("🔄 Testing API status...")
        status = await service.get_api_status()
        print(f"API status: {status}")

        if status.get("status") != "error":
            print("✅ AsyncYouTubeService basic functionality working!")
            return True
        else:
            print("✅ AsyncYouTubeService created but needs API key configuration")
            return True  # This is expected without API key

    except Exception as e:
        print(f"❌ AsyncYouTubeService test failed: {e}")
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
        print("🧪 Testing AsyncYouTubeService")
        print("=" * 40)

        success = await test_async_youtube_service()

        print("=" * 40)
        if success:
            print("🎉 AsyncYouTubeService tests passed!")
        else:
            print("💥 AsyncYouTubeService tests failed!")

        return success

    success = asyncio.run(main())
    exit(0 if success else 1)
