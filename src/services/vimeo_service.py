"""
Vimeo Music Video Service - Phase 3 Week 26
Integration with Vimeo for independent artists and high-quality music video content
"""

import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import quote, urljoin
import json

import httpx
from bs4 import BeautifulSoup

from src.services.settings_service import settings
from src.services.media_cache_manager import get_media_cache_manager, CacheType
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.vimeo_service")


class VimeoService:
    """Service for interacting with Vimeo for music video content"""
    
    def __init__(self):
        """Initialize Vimeo service"""
        self.base_url = "https://vimeo.com"
        self.api_base = "https://api.vimeo.com"
        self.rate_limit_delay = 1.5  # Vimeo is stricter on rate limits
        self.last_request_time = 0.0
        
        # HTTP client configuration
        self.timeout = httpx.Timeout(30.0, connect=10.0)
        self.headers = {
            'User-Agent': 'MVidarr/1.0 (Music Video Manager)',
            'Accept': 'application/json, text/html',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        # Vimeo API access token (if available)
        self._api_token = None
        
        logger.info("🎥 Vimeo service initialized")
    
    def get_api_token(self) -> Optional[str]:
        """Get Vimeo API token from settings"""
        try:
            from src.services.settings_service import SettingsService
            SettingsService.reload_cache()
            api_token = SettingsService.get("vimeo_api_token", "")
            self._api_token = api_token if api_token else None
            logger.debug(f"Vimeo API token: {'SET' if api_token else 'NOT SET'}")
            return self._api_token
        except Exception as e:
            logger.debug(f"Failed to get Vimeo API token: {e}")
            return None
    
    @property
    def api_token(self) -> Optional[str]:
        """Property to access API token consistently"""
        if self._api_token is None:
            return self.get_api_token()
        return self._api_token
    
    async def _rate_limit(self):
        """Implement rate limiting for Vimeo requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    async def _make_request(
        self, 
        url: str, 
        method: str = "GET", 
        use_api: bool = False,
        **kwargs
    ) -> Optional[httpx.Response]:
        """Make HTTP request to Vimeo with rate limiting and error handling"""
        await self._rate_limit()
        
        try:
            headers = self.headers.copy()
            
            # Add API authorization if using API and token available
            if use_api and self.api_token:
                headers['Authorization'] = f'Bearer {self.api_token}'
            
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
                
        except httpx.TimeoutException:
            logger.error(f"⏱️ Timeout requesting Vimeo URL: {url}")
            return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:  # Rate limited
                logger.warning(f"🚦 Vimeo rate limit hit, waiting longer...")
                await asyncio.sleep(self.rate_limit_delay * 2)
            logger.error(f"❌ HTTP error {e.response.status_code} requesting Vimeo URL: {url}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error requesting Vimeo URL {url}: {e}")
            return None
    
    async def search_independent_music_videos(
        self,
        artist: str,
        title: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search Vimeo for independent music videos
        
        Args:
            artist: Artist name to search for
            title: Optional song title
            limit: Maximum number of results
            
        Returns:
            List of independent music video data from Vimeo
        """
        start_time = time.time()
        
        try:
            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"vimeo_search_{quote(artist)}_{quote(title or '')}"
            
            cached_result = await cache_manager.get(CacheType.API_RESPONSE, cache_key)
            if cached_result:
                return cached_result
            
            # Build search query
            if title:
                query = f"{artist} {title} music video"
            else:
                query = f"{artist} music video"
            
            # Try API first if token available
            videos = []
            if self.api_token:
                videos = await self._search_via_api(query, limit)
            
            # Fallback to web scraping if API unavailable or failed
            if not videos:
                videos = await self._search_via_web(query, limit)
            
            # Enrich video data
            enriched_videos = []
            for video in videos[:limit]:
                try:
                    enriched_video = await self._get_video_details(video['vimeo_id'])
                    if enriched_video:
                        enriched_videos.append(enriched_video)
                    else:
                        enriched_videos.append(video)
                except Exception as e:
                    logger.warning(f"Failed to enrich Vimeo video {video.get('vimeo_id')}: {e}")
                    enriched_videos.append(video)
            
            # Cache results
            await cache_manager.set(
                CacheType.API_RESPONSE,
                cache_key,
                enriched_videos,
                ttl=3600  # 1 hour cache
            )
            
            # Track performance
            processing_time = time.time() - start_time
            await track_media_processing_time("vimeo_search", processing_time)
            
            logger.info(f"🎥 Found {len(enriched_videos)} Vimeo videos for '{query}'")
            return enriched_videos
            
        except Exception as e:
            logger.error(f"❌ Vimeo search failed for '{artist}' - '{title}': {e}")
            return []
    
    async def _search_via_api(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search using Vimeo API"""
        try:
            search_url = f"{self.api_base}/videos"
            params = {
                'query': query,
                'filter': 'CC',  # Creative Commons (more likely to be music content)
                'sort': 'relevant',
                'direction': 'desc',
                'per_page': min(limit, 50),  # Vimeo API limit
                'fields': 'uri,name,description,duration,created_time,modified_time,link,embed,pictures,tags,stats,user'
            }
            
            response = await self._make_request(search_url, params=params, use_api=True)
            if not response:
                return []
            
            api_data = response.json()
            videos = []
            
            for item in api_data.get('data', []):
                try:
                    # Extract Vimeo ID from URI
                    vimeo_id = item.get('uri', '').split('/')[-1]
                    if not vimeo_id.isdigit():
                        continue
                    
                    # Get thumbnail
                    pictures = item.get('pictures', {})
                    thumbnail_url = None
                    if pictures and pictures.get('sizes'):
                        # Get largest available thumbnail
                        thumbnail_url = pictures['sizes'][-1].get('link')
                    
                    # Check if this looks like a music video
                    name = item.get('name', '').lower()
                    description = item.get('description', '').lower()
                    tags = [tag.get('name', '').lower() for tag in item.get('tags', [])]
                    
                    # Simple music video detection
                    music_indicators = ['music', 'video', 'song', 'band', 'artist', 'official']
                    has_music_content = any(
                        indicator in name or indicator in description or indicator in ' '.join(tags)
                        for indicator in music_indicators
                    )
                    
                    if has_music_content:
                        video_data = {
                            'vimeo_id': vimeo_id,
                            'title': item.get('name', 'Unknown Title'),
                            'description': item.get('description', ''),
                            'duration': item.get('duration', 0),
                            'url': item.get('link', ''),
                            'embed_url': item.get('embed', {}).get('html', ''),
                            'thumbnail_url': thumbnail_url,
                            'created_time': item.get('created_time', ''),
                            'view_count': item.get('stats', {}).get('plays', 0),
                            'like_count': item.get('stats', {}).get('likes', 0),
                            'user': item.get('user', {}).get('name', 'Unknown'),
                            'tags': [tag.get('name', '') for tag in item.get('tags', [])],
                            'source': 'vimeo',
                            'platform': 'vimeo',
                            'quality': 'hd'
                        }
                        videos.append(video_data)
                        
                except Exception as e:
                    logger.debug(f"Failed to parse Vimeo API result: {e}")
                    continue
            
            return videos
            
        except Exception as e:
            logger.error(f"❌ Vimeo API search failed: {e}")
            return []
    
    async def _search_via_web(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search using web scraping as fallback"""
        try:
            search_url = f"{self.base_url}/search"
            params = {'q': query, 'type': 'video'}
            
            response = await self._make_request(search_url, params=params)
            if not response:
                return []
            
            # Parse search results from HTML
            videos = await self._parse_search_results(response.text, limit)
            return videos
            
        except Exception as e:
            logger.error(f"❌ Vimeo web search failed: {e}")
            return []
    
    async def _parse_search_results(self, html_content: str, limit: int) -> List[Dict[str, Any]]:
        """Parse Vimeo search results from HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            videos = []
            
            # Look for video containers in Vimeo's HTML structure
            video_elements = soup.find_all(['div', 'article'], class_=re.compile(r'video|result|clip'))
            
            for element in video_elements[:limit]:
                try:
                    video_data = await self._extract_video_from_element(element)
                    if video_data:
                        videos.append(video_data)
                except Exception as e:
                    logger.debug(f"Failed to parse video element: {e}")
                    continue
            
            return videos
            
        except Exception as e:
            logger.error(f"❌ Failed to parse Vimeo search results: {e}")
            return []
    
    async def _extract_video_from_element(self, element) -> Optional[Dict[str, Any]]:
        """Extract video information from HTML element"""
        try:
            # Look for video links
            link = element.find('a', href=re.compile(r'/\d+'))
            if not link:
                return None
            
            href = link.get('href', '')
            if not href:
                return None
            
            # Extract Vimeo ID from URL
            vimeo_id_match = re.search(r'/(\d+)', href)
            if not vimeo_id_match:
                return None
            
            vimeo_id = vimeo_id_match.group(1)
            
            # Extract title
            title_element = link.find(['h2', 'h3', 'span'], class_=re.compile(r'title'))
            if not title_element:
                title_element = link
            title = title_element.get_text(strip=True) if title_element else "Unknown Title"
            
            # Look for thumbnail
            img_element = element.find('img')
            thumbnail_url = None
            if img_element:
                thumbnail_url = img_element.get('src') or img_element.get('data-src')
            
            # Look for user/channel info
            user_element = element.find(['span', 'div'], class_=re.compile(r'user|author|channel'))
            user = user_element.get_text(strip=True) if user_element else "Unknown User"
            
            return {
                'vimeo_id': vimeo_id,
                'title': title,
                'user': user,
                'url': urljoin(self.base_url, href),
                'thumbnail_url': thumbnail_url,
                'source': 'vimeo',
                'platform': 'vimeo',
                'quality': 'hd',
                'independent': True  # Assume Vimeo content is independent
            }
            
        except Exception as e:
            logger.debug(f"Failed to extract video from element: {e}")
            return None
    
    async def get_video_details(self, vimeo_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific Vimeo video"""
        start_time = time.time()
        
        try:
            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"vimeo_video_{vimeo_id}"
            
            cached_result = await cache_manager.get(CacheType.API_RESPONSE, cache_key)
            if cached_result:
                return cached_result
            
            # Try API first if available
            video_details = None
            if self.api_token:
                video_details = await self._get_video_details_api(vimeo_id)
            
            # Fallback to web scraping
            if not video_details:
                video_details = await self._get_video_details_web(vimeo_id)
            
            if video_details:
                # Cache results
                await cache_manager.set(
                    CacheType.API_RESPONSE,
                    cache_key,
                    video_details,
                    ttl=7200  # 2 hour cache for detailed video info
                )
                
                # Track performance
                processing_time = time.time() - start_time
                await track_media_processing_time("vimeo_video_details", processing_time)
            
            return video_details
            
        except Exception as e:
            logger.error(f"❌ Failed to get Vimeo video details for {vimeo_id}: {e}")
            return None
    
    async def _get_video_details_api(self, vimeo_id: str) -> Optional[Dict[str, Any]]:
        """Get video details using Vimeo API"""
        try:
            video_url = f"{self.api_base}/videos/{vimeo_id}"
            params = {
                'fields': 'uri,name,description,duration,created_time,modified_time,link,embed,pictures,tags,stats,user,files,download'
            }
            
            response = await self._make_request(video_url, params=params, use_api=True)
            if not response:
                return None
            
            api_data = response.json()
            
            # Extract comprehensive data
            pictures = api_data.get('pictures', {})
            thumbnail_url = None
            if pictures and pictures.get('sizes'):
                # Get largest available thumbnail
                thumbnail_url = pictures['sizes'][-1].get('link')
            
            # Get available video qualities
            files = api_data.get('files', [])
            available_qualities = []
            best_quality = None
            
            for file_info in files:
                if file_info.get('quality'):
                    quality = file_info.get('quality')
                    available_qualities.append(quality)
                    if not best_quality or self._is_better_quality(quality, best_quality):
                        best_quality = quality
            
            video_details = {
                'vimeo_id': vimeo_id,
                'title': api_data.get('name', 'Unknown Title'),
                'description': api_data.get('description', ''),
                'duration': api_data.get('duration', 0),
                'url': api_data.get('link', ''),
                'embed_url': api_data.get('embed', {}).get('html', ''),
                'thumbnail_url': thumbnail_url,
                'created_time': api_data.get('created_time', ''),
                'view_count': api_data.get('stats', {}).get('plays', 0),
                'like_count': api_data.get('stats', {}).get('likes', 0),
                'comment_count': api_data.get('stats', {}).get('comments', 0),
                'user': api_data.get('user', {}).get('name', 'Unknown'),
                'user_url': api_data.get('user', {}).get('link', ''),
                'tags': [tag.get('name', '') for tag in api_data.get('tags', [])],
                'available_qualities': available_qualities,
                'best_quality': best_quality,
                'source': 'vimeo',
                'platform': 'vimeo',
                'independent': True,
                'hd_available': 'hd' in [q.lower() for q in available_qualities],
                '4k_available': any('4k' in q.lower() or '2160' in q for q in available_qualities)
            }
            
            return video_details
            
        except Exception as e:
            logger.error(f"❌ Failed to get Vimeo video details via API for {vimeo_id}: {e}")
            return None
    
    async def _get_video_details_web(self, vimeo_id: str) -> Optional[Dict[str, Any]]:
        """Get video details using web scraping"""
        try:
            video_url = f"{self.base_url}/{vimeo_id}"
            response = await self._make_request(video_url)
            
            if not response:
                return None
            
            # Parse video details from HTML
            video_details = await self._parse_video_page(response.text, vimeo_id)
            return video_details
            
        except Exception as e:
            logger.error(f"❌ Failed to get Vimeo video details via web for {vimeo_id}: {e}")
            return None
    
    async def _parse_video_page(self, html_content: str, vimeo_id: str) -> Optional[Dict[str, Any]]:
        """Parse video details from Vimeo video page"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for JSON-LD structured data
            json_scripts = soup.find_all('script', type='application/ld+json')
            video_data = None
            
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    if data.get('@type') == 'VideoObject':
                        video_data = data
                        break
                except:
                    continue
            
            # Initialize result
            result = {
                'vimeo_id': vimeo_id,
                'source': 'vimeo',
                'platform': 'vimeo',
                'independent': True
            }
            
            if video_data:
                # Extract from JSON-LD
                result.update({
                    'title': video_data.get('name', ''),
                    'description': video_data.get('description', ''),
                    'duration': self._parse_duration(video_data.get('duration', '')),
                    'upload_date': video_data.get('uploadDate', ''),
                    'thumbnail_url': video_data.get('thumbnailUrl', ''),
                    'embed_url': video_data.get('embedUrl', ''),
                    'view_count': video_data.get('interactionStatistic', {}).get('userInteractionCount', 0)
                })
            else:
                # Fallback to HTML parsing
                title_element = soup.find(['h1', 'h2'], class_=re.compile(r'title'))
                result['title'] = title_element.get_text(strip=True) if title_element else 'Unknown Title'
                
                # Look for description
                desc_element = soup.find(['div', 'p'], class_=re.compile(r'description'))
                result['description'] = desc_element.get_text(strip=True) if desc_element else ''
            
            # Add Vimeo-specific metadata
            result.update({
                'url': f"{self.base_url}/{vimeo_id}",
                'hd_available': True,  # Most Vimeo content is HD
                'high_quality': True   # Vimeo is known for quality
            })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to parse Vimeo video page for {vimeo_id}: {e}")
            return None
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration to seconds"""
        try:
            if duration_str.startswith('PT'):
                duration_str = duration_str[2:]
                
                minutes = 0
                seconds = 0
                
                if 'M' in duration_str:
                    min_match = re.search(r'(\d+)M', duration_str)
                    if min_match:
                        minutes = int(min_match.group(1))
                
                if 'S' in duration_str:
                    sec_match = re.search(r'(\d+)S', duration_str)
                    if sec_match:
                        seconds = int(sec_match.group(1))
                
                return minutes * 60 + seconds
            
            return 0
            
        except:
            return 0
    
    def _is_better_quality(self, quality1: str, quality2: str) -> bool:
        """Determine if quality1 is better than quality2"""
        quality_order = ['mobile', 'sd', 'hd', '720p', '1080p', '4k', '2160p']
        
        try:
            q1_index = next((i for i, q in enumerate(quality_order) if q in quality1.lower()), -1)
            q2_index = next((i for i, q in enumerate(quality_order) if q in quality2.lower()), -1)
            
            return q1_index > q2_index
        except:
            return False
    
    async def find_exclusive_artist_channels(self, artist_name: str) -> List[Dict[str, Any]]:
        """Find exclusive artist channels on Vimeo"""
        start_time = time.time()
        
        try:
            # Search for channels/users
            if self.api_token:
                search_url = f"{self.api_base}/users"
                params = {
                    'query': artist_name,
                    'sort': 'relevant',
                    'direction': 'desc',
                    'per_page': 20
                }
                
                response = await self._make_request(search_url, params=params, use_api=True)
                if response:
                    api_data = response.json()
                    channels = []
                    
                    for user in api_data.get('data', []):
                        if artist_name.lower() in user.get('name', '').lower():
                            channel_data = {
                                'user_id': user.get('uri', '').split('/')[-1],
                                'name': user.get('name', ''),
                                'bio': user.get('bio', ''),
                                'url': user.get('link', ''),
                                'video_count': user.get('metadata', {}).get('connections', {}).get('videos', {}).get('total', 0),
                                'follower_count': user.get('metadata', {}).get('connections', {}).get('followers', {}).get('total', 0),
                                'verified': user.get('account', '') in ['plus', 'pro', 'business', 'premium']
                            }
                            channels.append(channel_data)
                    
                    # Track performance
                    processing_time = time.time() - start_time
                    await track_media_processing_time("vimeo_find_channels", processing_time)
                    
                    logger.info(f"🎥 Found {len(channels)} potential Vimeo channels for {artist_name}")
                    return channels
            
            return []
            
        except Exception as e:
            logger.error(f"❌ Failed to find Vimeo artist channels for {artist_name}: {e}")
            return []
    
    async def get_high_quality_video_streams(self, vimeo_id: str) -> Dict[str, Any]:
        """Get high quality video streams for a Vimeo video"""
        try:
            if not self.api_token:
                logger.warning("Vimeo API token required for high quality stream access")
                return {}
            
            video_url = f"{self.api_base}/videos/{vimeo_id}"
            params = {'fields': 'files,download'}
            
            response = await self._make_request(video_url, params=params, use_api=True)
            if not response:
                return {}
            
            api_data = response.json()
            files = api_data.get('files', [])
            
            streams = {}
            for file_info in files:
                quality = file_info.get('quality', 'unknown')
                link = file_info.get('link')
                
                if link:
                    streams[quality] = {
                        'url': link,
                        'quality': quality,
                        'width': file_info.get('width', 0),
                        'height': file_info.get('height', 0),
                        'fps': file_info.get('fps', 0),
                        'size': file_info.get('size', 0)
                    }
            
            return streams
            
        except Exception as e:
            logger.error(f"❌ Failed to get Vimeo video streams for {vimeo_id}: {e}")
            return {}
    
    async def get_service_statistics(self) -> Dict[str, Any]:
        """Get Vimeo service performance statistics"""
        try:
            cache_manager = await get_media_cache_manager()
            
            return {
                "service": "Vimeo",
                "base_url": self.base_url,
                "api_available": self.api_token is not None,
                "rate_limit_delay": self.rate_limit_delay,
                "last_request_time": self.last_request_time,
                "cache_stats": await cache_manager.get_statistics(),
                "capabilities": {
                    "independent_videos": True,
                    "high_quality_content": True,
                    "artist_channels": True,
                    "api_integration": self.api_token is not None,
                    "quality_streams": self.api_token is not None
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get Vimeo service statistics: {e}")
            return {"service": "Vimeo", "error": str(e)}
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to Vimeo"""
        try:
            response = await self._make_request(self.base_url)
            
            if response and response.status_code == 200:
                result = {
                    "status": "success",
                    "message": "Successfully connected to Vimeo",
                    "response_time_ms": response.elapsed.total_seconds() * 1000,
                    "web_access": True
                }
                
                # Test API access if token available
                if self.api_token:
                    api_response = await self._make_request(f"{self.api_base}/me", use_api=True)
                    result["api_access"] = api_response is not None and api_response.status_code == 200
                else:
                    result["api_access"] = False
                    result["api_note"] = "No API token configured"
                
                return result
            else:
                return {
                    "status": "error",
                    "message": f"Failed to connect to Vimeo - Status: {response.status_code if response else 'No response'}"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "message": f"Vimeo connection test failed: {str(e)}"
            }


# Global Vimeo service instance
vimeo_service = VimeoService()

# Async wrapper function for consistency with other services
async def get_vimeo_service() -> VimeoService:
    """Get Vimeo service instance"""
    return vimeo_service