"""
Vevo Service - Phase 3 Week 26
Integration with Vevo for official music video content discovery and metadata
"""

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.vevo_service")


class VevoService:
    """Service for interacting with Vevo to find official music videos"""

    def __init__(self):
        """Initialize Vevo service"""
        self.base_url = "https://www.vevo.com"
        self.api_base = "https://apiv2.vevo.com"
        self.rate_limit_delay = 1.0  # Seconds between requests
        self.last_request_time = 0.0

        # HTTP client configuration
        self.timeout = httpx.Timeout(30.0, connect=10.0)
        self.headers = {
            "User-Agent": "MVidarr/1.0 (Music Video Manager)",
            "Accept": "application/json, text/html",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        logger.info("🎬 Vevo service initialized")

    async def _rate_limit(self):
        """Implement rate limiting for Vevo requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    async def _make_request(
        self, url: str, method: str = "GET", **kwargs
    ) -> Optional[httpx.Response]:
        """Make HTTP request to Vevo with rate limiting and error handling"""
        await self._rate_limit()

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, headers=self.headers
            ) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response

        except httpx.TimeoutException:
            logger.error(f"⏱️ Timeout requesting Vevo URL: {url}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(
                f"❌ HTTP error {e.response.status_code} requesting Vevo URL: {url}"
            )
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error requesting Vevo URL {url}: {e}")
            return None

    async def search_official_music_videos(
        self, artist: str, title: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search Vevo for official music videos

        Args:
            artist: Artist name to search for
            title: Optional song title to search for
            limit: Maximum number of results to return

        Returns:
            List of official music video data from Vevo
        """
        start_time = time.time()

        try:
            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"vevo_search_{quote(artist)}_{quote(title or '')}"

            cached_result = await cache_manager.get(CacheType.API_RESPONSE, cache_key)
            if cached_result:
                return cached_result

            # Build search query
            if title:
                query = f"{artist} {title}"
            else:
                query = artist

            # Search through Vevo's web interface (no public API)
            search_url = f"{self.base_url}/search"
            search_params = {"q": query, "category": "video"}

            response = await self._make_request(search_url, params=search_params)
            if not response:
                return []

            # Parse search results from HTML
            videos = await self._parse_search_results(response.text, limit)

            # Enrich video data with additional metadata
            enriched_videos = []
            for video in videos[:limit]:
                try:
                    enriched_video = await self._get_video_details(video["vevo_id"])
                    if enriched_video:
                        enriched_videos.append(enriched_video)
                except Exception as e:
                    logger.warning(
                        f"Failed to enrich Vevo video {video.get('vevo_id')}: {e}"
                    )
                    enriched_videos.append(video)

            # Cache results
            await cache_manager.set(
                CacheType.API_RESPONSE,
                cache_key,
                enriched_videos,
                ttl=3600,  # 1 hour cache
            )

            # Track performance
            processing_time = time.time() - start_time
            await track_media_processing_time("vevo_search", processing_time)

            logger.info(f"🎬 Found {len(enriched_videos)} Vevo videos for '{query}'")
            return enriched_videos

        except Exception as e:
            logger.error(f"❌ Vevo search failed for '{artist}' - '{title}': {e}")
            return []

    async def _parse_search_results(
        self, html_content: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Parse Vevo search results from HTML"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            videos = []

            # Look for video containers in Vevo's HTML structure
            video_elements = soup.find_all(
                ["div", "article"], class_=re.compile(r"video|result|item")
            )

            for element in video_elements[:limit]:
                try:
                    # Extract video data from HTML
                    video_data = await self._extract_video_from_element(element)
                    if video_data:
                        videos.append(video_data)
                except Exception as e:
                    logger.debug(f"Failed to parse video element: {e}")
                    continue

            return videos

        except Exception as e:
            logger.error(f"❌ Failed to parse Vevo search results: {e}")
            return []

    async def _extract_video_from_element(self, element) -> Optional[Dict[str, Any]]:
        """Extract video information from HTML element"""
        try:
            # Look for video links and metadata
            link = element.find("a", href=re.compile(r"/watch/"))
            if not link:
                return None

            href = link.get("href", "")
            if not href:
                return None

            # Extract Vevo ID from URL
            vevo_id_match = re.search(r"/watch/([A-Z0-9]+)", href)
            if not vevo_id_match:
                return None

            vevo_id = vevo_id_match.group(1)

            # Extract title and artist from link text or nearby elements
            title_element = link.find(["h2", "h3", "span"], class_=re.compile(r"title"))
            title = (
                title_element.get_text(strip=True) if title_element else "Unknown Title"
            )

            # Look for artist information
            artist_element = element.find(["span", "div"], class_=re.compile(r"artist"))
            artist = (
                artist_element.get_text(strip=True)
                if artist_element
                else "Unknown Artist"
            )

            # Look for thumbnail
            img_element = element.find("img")
            thumbnail_url = (
                img_element.get("src") or img_element.get("data-src")
                if img_element
                else None
            )

            return {
                "vevo_id": vevo_id,
                "title": title,
                "artist": artist,
                "url": urljoin(self.base_url, href),
                "thumbnail_url": thumbnail_url,
                "source": "vevo",
                "official": True,  # All Vevo content is official
                "quality": "hd",  # Vevo provides high-quality content
            }

        except Exception as e:
            logger.debug(f"Failed to extract video from element: {e}")
            return None

    async def get_video_details(self, vevo_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific Vevo video"""
        start_time = time.time()

        try:
            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"vevo_video_{vevo_id}"

            cached_result = await cache_manager.get(CacheType.API_RESPONSE, cache_key)
            if cached_result:
                return cached_result

            # Get video page
            video_url = f"{self.base_url}/watch/{vevo_id}"
            response = await self._make_request(video_url)

            if not response:
                return None

            # Parse video details from HTML
            video_details = await self._parse_video_page(response.text, vevo_id)

            if video_details:
                # Cache results
                await cache_manager.set(
                    CacheType.API_RESPONSE,
                    cache_key,
                    video_details,
                    ttl=7200,  # 2 hour cache for detailed video info
                )

                # Track performance
                processing_time = time.time() - start_time
                await track_media_processing_time("vevo_video_details", processing_time)

            return video_details

        except Exception as e:
            logger.error(f"❌ Failed to get Vevo video details for {vevo_id}: {e}")
            return None

    async def _parse_video_page(
        self, html_content: str, vevo_id: str
    ) -> Optional[Dict[str, Any]]:
        """Parse video details from Vevo video page"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Look for JSON-LD structured data
            json_scripts = soup.find_all("script", type="application/ld+json")
            video_data = None

            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    if data.get("@type") == "VideoObject":
                        video_data = data
                        break
                except:
                    continue

            # Extract video information
            result = {
                "vevo_id": vevo_id,
                "source": "vevo",
                "official": True,
                "quality": "hd",
            }

            if video_data:
                # Extract from JSON-LD
                result.update(
                    {
                        "title": video_data.get("name", ""),
                        "description": video_data.get("description", ""),
                        "duration": self._parse_duration(
                            video_data.get("duration", "")
                        ),
                        "upload_date": video_data.get("uploadDate", ""),
                        "thumbnail_url": video_data.get("thumbnailUrl", ""),
                        "embed_url": video_data.get("embedUrl", ""),
                        "view_count": video_data.get("interactionStatistic", {}).get(
                            "userInteractionCount", 0
                        ),
                    }
                )

                # Extract artist from performer or creator
                if "performer" in video_data:
                    result["artist"] = video_data["performer"].get("name", "")
                elif "creator" in video_data:
                    result["artist"] = video_data["creator"].get("name", "")

            else:
                # Fallback to HTML parsing
                title_element = soup.find(["h1", "h2"], class_=re.compile(r"title"))
                result["title"] = (
                    title_element.get_text(strip=True)
                    if title_element
                    else "Unknown Title"
                )

                artist_element = soup.find(
                    ["span", "div"], class_=re.compile(r"artist")
                )
                result["artist"] = (
                    artist_element.get_text(strip=True)
                    if artist_element
                    else "Unknown Artist"
                )

                # Look for video metadata
                meta_description = soup.find("meta", attrs={"name": "description"})
                if meta_description:
                    result["description"] = meta_description.get("content", "")

            # Add Vevo-specific metadata
            result.update(
                {
                    "url": f"{self.base_url}/watch/{vevo_id}",
                    "platform": "vevo",
                    "official": True,
                    "verified": True,
                    "hd_available": True,
                    "4k_available": False,  # Would need additional detection
                }
            )

            return result

        except Exception as e:
            logger.error(f"❌ Failed to parse Vevo video page for {vevo_id}: {e}")
            return None

    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration to seconds"""
        try:
            # Handle format like "PT3M45S"
            if duration_str.startswith("PT"):
                duration_str = duration_str[2:]

                minutes = 0
                seconds = 0

                if "M" in duration_str:
                    min_match = re.search(r"(\d+)M", duration_str)
                    if min_match:
                        minutes = int(min_match.group(1))

                if "S" in duration_str:
                    sec_match = re.search(r"(\d+)S", duration_str)
                    if sec_match:
                        seconds = int(sec_match.group(1))

                return minutes * 60 + seconds

            return 0

        except:
            return 0

    async def get_vevo_channel_videos(
        self, artist_name: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get all music videos from a Vevo artist channel"""
        start_time = time.time()

        try:
            # Search for artist's Vevo channel
            channel_url = (
                f"{self.base_url}/artist/{quote(artist_name.lower().replace(' ', '-'))}"
            )

            response = await self._make_request(channel_url)
            if not response:
                # Fallback to search if direct channel doesn't work
                return await self.search_official_music_videos(artist_name, limit=limit)

            # Parse channel page for videos
            videos = await self._parse_channel_videos(response.text, limit)

            # Track performance
            processing_time = time.time() - start_time
            await track_media_processing_time("vevo_channel_videos", processing_time)

            logger.info(f"🎬 Found {len(videos)} videos on {artist_name}'s Vevo channel")
            return videos

        except Exception as e:
            logger.error(f"❌ Failed to get Vevo channel videos for {artist_name}: {e}")
            return []

    async def _parse_channel_videos(
        self, html_content: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Parse videos from artist channel page"""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            videos = []

            # Look for video grid or list elements
            video_elements = soup.find_all(
                ["div", "article"], class_=re.compile(r"video|item")
            )

            for element in video_elements[:limit]:
                video_data = await self._extract_video_from_element(element)
                if video_data:
                    videos.append(video_data)

            return videos

        except Exception as e:
            logger.error(f"❌ Failed to parse Vevo channel videos: {e}")
            return []

    async def verify_official_video_status(self, video_data: Dict[str, Any]) -> bool:
        """Verify if a video is an official music video on Vevo"""
        try:
            if video_data.get("source") == "vevo":
                return True  # All Vevo content is official

            # For videos from other sources, try to find them on Vevo
            artist = video_data.get("artist", "")
            title = video_data.get("title", "")

            if not artist or not title:
                return False

            vevo_videos = await self.search_official_music_videos(
                artist, title, limit=3
            )

            # Check for title similarity
            for vevo_video in vevo_videos:
                if self._titles_match(title, vevo_video.get("title", "")):
                    return True

            return False

        except Exception as e:
            logger.error(f"❌ Failed to verify official video status: {e}")
            return False

    def _titles_match(self, title1: str, title2: str, threshold: float = 0.8) -> bool:
        """Check if two video titles are similar enough to be the same song"""
        try:
            # Simple similarity check - clean and compare
            clean_title1 = re.sub(r"[^\w\s]", "", title1.lower()).strip()
            clean_title2 = re.sub(r"[^\w\s]", "", title2.lower()).strip()

            # Remove common video suffixes
            for suffix in [
                "official video",
                "official music video",
                "music video",
                "official",
            ]:
                clean_title1 = clean_title1.replace(suffix, "").strip()
                clean_title2 = clean_title2.replace(suffix, "").strip()

            # Simple word matching
            words1 = set(clean_title1.split())
            words2 = set(clean_title2.split())

            if not words1 or not words2:
                return False

            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))

            similarity = intersection / union if union > 0 else 0
            return similarity >= threshold

        except Exception as e:
            logger.debug(f"Title matching error: {e}")
            return False

    async def get_service_statistics(self) -> Dict[str, Any]:
        """Get Vevo service performance statistics"""
        try:
            cache_manager = await get_media_cache_manager()

            return {
                "service": "Vevo",
                "base_url": self.base_url,
                "rate_limit_delay": self.rate_limit_delay,
                "last_request_time": self.last_request_time,
                "cache_stats": await cache_manager.get_statistics(),
                "capabilities": {
                    "official_videos": True,
                    "hd_quality": True,
                    "artist_channels": True,
                    "video_verification": True,
                    "metadata_enrichment": True,
                },
            }

        except Exception as e:
            logger.error(f"❌ Failed to get Vevo service statistics: {e}")
            return {"service": "Vevo", "error": str(e)}

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to Vevo"""
        try:
            response = await self._make_request(self.base_url)

            if response and response.status_code == 200:
                return {
                    "status": "success",
                    "message": "Successfully connected to Vevo",
                    "response_time_ms": response.elapsed.total_seconds() * 1000,
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to connect to Vevo - Status: {response.status_code if response else 'No response'}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Vevo connection test failed: {str(e)}",
            }


# Global Vevo service instance
vevo_service = VevoService()


# Async wrapper function for consistency with other services
async def get_vevo_service() -> VevoService:
    """Get Vevo service instance"""
    return vevo_service
