"""
Mobile Web Service - Phase 4 Week 31
Enhanced mobile web interface with offline capabilities for personal music video collections
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import selectinload
from src.database.async_connection import get_async_session
from src.database.models import Video
from src.services.playlist_management_service import get_playlist_management_service
from src.services.redis_service import get_redis_client
from src.services.video_browser_service import get_video_browser_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.mobile_web")


class MobileViewMode(Enum):
    """Mobile-optimized view modes"""

    CARDS = "cards"  # Card-based interface
    LIST = "list"  # Compact list view
    GRID = "grid"  # Touch-friendly grid
    OFFLINE = "offline"  # Offline-cached content


class OfflineStrategy(Enum):
    """Offline caching strategies"""

    FAVORITES_ONLY = "favorites_only"  # Cache user favorites
    RECENT_WATCHED = "recent_watched"  # Cache recently watched
    PLAYLISTS = "playlists"  # Cache specific playlists
    SMART_CACHE = "smart_cache"  # Intelligent caching based on usage
    MANUAL_SELECTION = "manual_selection"  # User manually selects videos


class MobileQuality(Enum):
    """Mobile-optimized quality levels"""

    LOW_480P = "480p"  # Low bandwidth/storage
    MEDIUM_720P = "720p"  # Balanced quality/size
    HIGH_1080P = "1080p"  # High quality for Wi-Fi
    AUTO = "auto"  # Adaptive based on connection


@dataclass
class MobileVideoCard:
    """Mobile-optimized video card"""

    video_id: int
    title: str
    artist_name: str
    duration: int
    thumbnail_url: str
    is_cached: bool
    cache_size_mb: float
    quality_available: List[str]
    is_favorite: bool
    last_watched_position: int
    download_progress: Optional[float] = None  # 0-100 if downloading


@dataclass
class OfflineCacheItem:
    """Offline cached video item"""

    video_id: int
    title: str
    artist_name: str
    file_path: str
    thumbnail_path: str
    cache_size_mb: float
    cached_at: datetime
    last_accessed: datetime
    quality: str
    expires_at: Optional[datetime] = None


@dataclass
class MobileStats:
    """Mobile app statistics"""

    total_videos_cached: int
    total_cache_size_mb: float
    available_storage_mb: float
    cache_hit_rate: float
    offline_play_count: int
    sync_last_updated: datetime
    bandwidth_saved_mb: float


class MobileWebService:
    """Mobile web interface with offline capabilities"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.video_browser = None
        self.playlist_service = None

        # Mobile configuration
        self.mobile_cache_dir = "/data/mobile_cache"
        self.max_cache_size_mb = 2048  # 2GB default cache limit
        self.cache_retention_days = 30  # Keep cached items for 30 days
        self.thumbnail_cache_size = (150, 150)  # Mobile thumbnail size

        # Quality settings for mobile
        self.mobile_bitrates = {
            MobileQuality.LOW_480P: 800,  # 800kbps
            MobileQuality.MEDIUM_720P: 1500,  # 1.5Mbps
            MobileQuality.HIGH_1080P: 3000,  # 3Mbps
        }

        # Offline sync settings
        self.sync_batch_size = 5  # Download 5 videos at a time
        self.auto_sync_on_wifi = True
        self.background_sync_enabled = True

    async def initialize(self):
        """Initialize mobile web service"""
        try:
            self.redis_client = await get_redis_client()
            self.video_browser = await get_video_browser_service()
            self.playlist_service = await get_playlist_management_service()

            # Ensure cache directories exist
            os.makedirs(self.mobile_cache_dir, exist_ok=True)
            os.makedirs(f"{self.mobile_cache_dir}/videos", exist_ok=True)
            os.makedirs(f"{self.mobile_cache_dir}/thumbnails", exist_ok=True)

            logger.info("Mobile web service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize mobile web service: {e}")
            raise

    async def get_mobile_dashboard(
        self,
        user_id: Optional[int] = None,
        view_mode: MobileViewMode = MobileViewMode.CARDS,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get mobile-optimized dashboard"""
        try:
            dashboard = {
                "recent_videos": [],
                "continue_watching": [],
                "favorite_playlists": [],
                "offline_content": [],
                "quick_actions": [],
                "stats": {},
                "view_mode": view_mode.value,
            }

            # Get recent videos with mobile optimization
            recent_videos = await self._get_recent_mobile_videos(limit=10)
            dashboard["recent_videos"] = recent_videos

            # Get continue watching
            continue_watching = await self._get_continue_watching_mobile(
                user_id, limit=5
            )
            dashboard["continue_watching"] = continue_watching

            # Get favorite playlists
            favorite_playlists = await self._get_favorite_playlists_mobile(
                user_id, limit=3
            )
            dashboard["favorite_playlists"] = favorite_playlists

            # Get offline content
            offline_content = await self._get_offline_content_summary()
            dashboard["offline_content"] = offline_content

            # Generate quick actions
            dashboard["quick_actions"] = await self._get_mobile_quick_actions(user_id)

            # Get mobile stats
            dashboard["stats"] = await self.get_mobile_stats(user_id)

            return dashboard

        except Exception as e:
            logger.error(f"Failed to get mobile dashboard: {e}")
            return {"error": str(e)}

    async def browse_mobile_videos(
        self,
        page: int = 1,
        per_page: int = 20,
        view_mode: MobileViewMode = MobileViewMode.CARDS,
        filters: Optional[Dict[str, Any]] = None,
        include_offline: bool = True,
    ) -> Dict[str, Any]:
        """Browse videos with mobile optimization"""
        try:
            # Adjust per_page for mobile (smaller batches)
            per_page = min(per_page, 50)
            filters = filters or {}

            # Get videos using existing browser service
            video_results = await self.video_browser.browse_videos(
                page=page,
                per_page=per_page,
                view_mode=f"mobile_{view_mode.value}",
                sort_option=filters.get("sort", "recently_added"),
                filters=filters,
            )

            # Convert to mobile cards
            mobile_cards = []
            for video in video_results.get("videos", []):
                mobile_card = await self._create_mobile_video_card(
                    video, include_offline
                )
                mobile_cards.append(mobile_card)

            # Add offline content if requested
            if include_offline and view_mode == MobileViewMode.OFFLINE:
                offline_cards = await self._get_offline_video_cards()
                mobile_cards.extend(offline_cards)

            return {
                "videos": [card.__dict__ for card in mobile_cards],
                "total_count": video_results.get("total_count", 0),
                "page": page,
                "per_page": per_page,
                "total_pages": video_results.get("total_pages", 1),
                "has_next": video_results.get("has_next", False),
                "has_prev": video_results.get("has_prev", False),
                "view_mode": view_mode.value,
                "offline_enabled": include_offline,
            }

        except Exception as e:
            logger.error(f"Failed to browse mobile videos: {e}")
            return {"error": str(e)}

    async def cache_video_for_offline(
        self,
        video_id: int,
        quality: MobileQuality = MobileQuality.MEDIUM_720P,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Cache video for offline viewing"""
        try:
            # Check if already cached
            cached_item = await self._get_cached_video(video_id)
            if cached_item:
                return {
                    "success": True,
                    "message": "Video already cached",
                    "cache_item": cached_item.__dict__,
                }

            # Check cache space
            current_cache_size = await self._get_total_cache_size()
            if current_cache_size >= self.max_cache_size_mb:
                # Clean up old cache items
                await self._cleanup_old_cache_items()

                # Recheck space
                current_cache_size = await self._get_total_cache_size()
                if current_cache_size >= self.max_cache_size_mb:
                    return {"success": False, "message": "Insufficient cache space"}

            # Get video details
            async with get_async_session() as session:
                video_query = (
                    select(Video)
                    .where(Video.id == video_id)
                    .options(selectinload(Video.artist))
                )
                result = await session.execute(video_query)
                video = result.scalar_one_or_none()

                if not video:
                    return {"success": False, "message": f"Video {video_id} not found"}

                # Start caching process
                cache_result = await self._cache_video_file(video, quality)

                if cache_result["success"]:
                    # Update cache registry
                    cache_item = OfflineCacheItem(
                        video_id=video.id,
                        title=video.title or "Unknown Title",
                        artist_name=video.artist_name or "Unknown Artist",
                        file_path=cache_result["file_path"],
                        thumbnail_path=cache_result["thumbnail_path"],
                        cache_size_mb=cache_result["file_size_mb"],
                        cached_at=datetime.now(),
                        last_accessed=datetime.now(),
                        quality=quality.value,
                    )

                    await self._save_cache_item(cache_item)

                    return {
                        "success": True,
                        "message": "Video cached successfully",
                        "cache_item": cache_item.__dict__,
                    }

                return cache_result

        except Exception as e:
            logger.error(f"Failed to cache video {video_id}: {e}")
            return {"success": False, "message": f"Caching failed: {str(e)}"}

    async def sync_offline_content(
        self,
        strategy: OfflineStrategy = OfflineStrategy.SMART_CACHE,
        user_id: Optional[int] = None,
        max_videos: int = 20,
    ) -> Dict[str, Any]:
        """Sync content for offline viewing"""
        try:
            sync_results = {
                "strategy": strategy.value,
                "videos_processed": 0,
                "videos_cached": 0,
                "videos_failed": 0,
                "total_size_mb": 0.0,
                "sync_time": datetime.now().isoformat(),
            }

            # Get videos to cache based on strategy
            videos_to_cache = await self._get_videos_for_strategy(
                strategy, user_id, max_videos
            )

            sync_results["videos_processed"] = len(videos_to_cache)

            # Cache videos in batches
            for i in range(0, len(videos_to_cache), self.sync_batch_size):
                batch = videos_to_cache[i : i + self.sync_batch_size]

                batch_tasks = [
                    self.cache_video_for_offline(
                        video_id, MobileQuality.MEDIUM_720P, user_id
                    )
                    for video_id in batch
                ]

                batch_results = await asyncio.gather(
                    *batch_tasks, return_exceptions=True
                )

                for result in batch_results:
                    if isinstance(result, Exception):
                        sync_results["videos_failed"] += 1
                        logger.error(f"Failed to cache video in batch: {result}")
                    elif result.get("success"):
                        sync_results["videos_cached"] += 1
                        if "cache_item" in result:
                            sync_results["total_size_mb"] += result["cache_item"].get(
                                "cache_size_mb", 0
                            )
                    else:
                        sync_results["videos_failed"] += 1

            # Update sync statistics
            await self._update_sync_stats(sync_results)

            logger.info(
                f"Offline sync completed: {sync_results['videos_cached']} cached, {sync_results['videos_failed']} failed"
            )

            return sync_results

        except Exception as e:
            logger.error(f"Failed to sync offline content: {e}")
            return {"error": str(e)}

    async def get_mobile_stats(self, user_id: Optional[int] = None) -> MobileStats:
        """Get mobile app statistics"""
        try:
            # Get cache statistics
            cached_videos = await self._get_all_cached_videos()
            total_cache_size = sum(item.cache_size_mb for item in cached_videos)

            # Get available storage (simplified - would check actual disk space)
            available_storage = self.max_cache_size_mb - total_cache_size

            # Get cache hit rate from Redis
            cache_hits = await self.redis_client.get("mobile_cache_hits") or 0
            cache_misses = await self.redis_client.get("mobile_cache_misses") or 0
            total_requests = int(cache_hits) + int(cache_misses)
            cache_hit_rate = (
                (int(cache_hits) / total_requests * 100) if total_requests > 0 else 0
            )

            # Get offline play count
            offline_plays = await self.redis_client.get(f"offline_plays:{user_id}") or 0

            # Get last sync time
            last_sync = await self.redis_client.get("last_offline_sync")
            sync_time = (
                datetime.fromisoformat(last_sync) if last_sync else datetime.now()
            )

            return MobileStats(
                total_videos_cached=len(cached_videos),
                total_cache_size_mb=round(total_cache_size, 2),
                available_storage_mb=round(available_storage, 2),
                cache_hit_rate=round(cache_hit_rate, 1),
                offline_play_count=int(offline_plays),
                sync_last_updated=sync_time,
                bandwidth_saved_mb=round(
                    total_cache_size * 0.8, 2
                ),  # Estimate bandwidth savings
            )

        except Exception as e:
            logger.error(f"Failed to get mobile stats: {e}")
            return MobileStats(0, 0, 0, 0, 0, datetime.now(), 0)

    async def clear_offline_cache(
        self,
        video_ids: Optional[List[int]] = None,
        older_than_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Clear offline cache"""
        try:
            cleared_count = 0
            freed_space_mb = 0.0

            cached_videos = await self._get_all_cached_videos()

            for cached_item in cached_videos:
                should_clear = False

                # Clear specific videos
                if video_ids and cached_item.video_id in video_ids:
                    should_clear = True

                # Clear old videos
                if older_than_days:
                    age_days = (datetime.now() - cached_item.cached_at).days
                    if age_days > older_than_days:
                        should_clear = True

                # Clear all if no specific criteria
                if not video_ids and not older_than_days:
                    should_clear = True

                if should_clear:
                    await self._remove_cached_video(cached_item)
                    cleared_count += 1
                    freed_space_mb += cached_item.cache_size_mb

            logger.info(
                f"Cleared {cleared_count} cached videos, freed {freed_space_mb:.2f}MB"
            )

            return {
                "success": True,
                "cleared_count": cleared_count,
                "freed_space_mb": round(freed_space_mb, 2),
            }

        except Exception as e:
            logger.error(f"Failed to clear offline cache: {e}")
            return {"success": False, "error": str(e)}

    async def _get_recent_mobile_videos(self, limit: int = 10) -> List[MobileVideoCard]:
        """Get recent videos optimized for mobile"""
        try:
            async with get_async_session() as session:
                query = (
                    select(Video)
                    .options(selectinload(Video.artist))
                    .order_by(desc(Video.created_at))
                    .limit(limit)
                )
                result = await session.execute(query)
                videos = result.scalars().all()

                mobile_cards = []
                for video in videos:
                    card = await self._create_mobile_video_card(
                        {
                            "id": video.id,
                            "title": video.title,
                            "artist_name": video.artist_name,
                            "duration": video.duration,
                            "is_music_video": video.is_music_video,
                        }
                    )
                    mobile_cards.append(card)

                return mobile_cards

        except Exception as e:
            logger.error(f"Failed to get recent mobile videos: {e}")
            return []

    async def _create_mobile_video_card(
        self, video_data: Dict[str, Any], include_offline: bool = True
    ) -> MobileVideoCard:
        """Create mobile-optimized video card"""
        try:
            video_id = video_data["id"]

            # Check if cached offline
            is_cached = False
            cache_size_mb = 0.0
            if include_offline:
                cached_item = await self._get_cached_video(video_id)
                is_cached = cached_item is not None
                cache_size_mb = cached_item.cache_size_mb if cached_item else 0.0

            # Get available qualities (simplified)
            available_qualities = ["480p", "720p", "1080p"]

            # Check if favorite (simplified)
            is_favorite = False  # Would check user favorites

            # Get last watched position (simplified)
            last_watched_position = 0  # Would get from watch history

            return MobileVideoCard(
                video_id=video_id,
                title=video_data.get("title", "Unknown Title"),
                artist_name=video_data.get("artist_name", "Unknown Artist"),
                duration=video_data.get("duration", 0),
                thumbnail_url=f"/api/thumbnails/video/{video_id}/mobile",
                is_cached=is_cached,
                cache_size_mb=cache_size_mb,
                quality_available=available_qualities,
                is_favorite=is_favorite,
                last_watched_position=last_watched_position,
            )

        except Exception as e:
            logger.error(f"Failed to create mobile video card: {e}")
            return MobileVideoCard(
                video_id=video_data.get("id", 0),
                title="Error Loading Video",
                artist_name="Unknown",
                duration=0,
                thumbnail_url="",
                is_cached=False,
                cache_size_mb=0.0,
                quality_available=[],
                is_favorite=False,
                last_watched_position=0,
            )

    async def _get_cached_video(self, video_id: int) -> Optional[OfflineCacheItem]:
        """Get cached video item"""
        try:
            cache_key = f"mobile_cache_item:{video_id}"
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                return OfflineCacheItem(
                    video_id=data["video_id"],
                    title=data["title"],
                    artist_name=data["artist_name"],
                    file_path=data["file_path"],
                    thumbnail_path=data["thumbnail_path"],
                    cache_size_mb=data["cache_size_mb"],
                    cached_at=datetime.fromisoformat(data["cached_at"]),
                    last_accessed=datetime.fromisoformat(data["last_accessed"]),
                    quality=data["quality"],
                    expires_at=(
                        datetime.fromisoformat(data["expires_at"])
                        if data.get("expires_at")
                        else None
                    ),
                )

            return None

        except Exception as e:
            logger.error(f"Failed to get cached video {video_id}: {e}")
            return None

    async def _cache_video_file(
        self, video: Video, quality: MobileQuality
    ) -> Dict[str, Any]:
        """Cache video file for offline viewing"""
        try:
            # This is a placeholder implementation
            # In reality, you'd transcode/copy the video file to the mobile cache

            video_filename = f"video_{video.id}_{quality.value}.mp4"
            thumbnail_filename = f"thumb_{video.id}_mobile.jpg"

            video_path = f"{self.mobile_cache_dir}/videos/{video_filename}"
            thumbnail_path = f"{self.mobile_cache_dir}/thumbnails/{thumbnail_filename}"

            # Simulate file caching (would actually copy/transcode files)
            file_size_mb = 50.0  # Placeholder file size

            # Create placeholder files for demo
            Path(video_path).touch()
            Path(thumbnail_path).touch()

            return {
                "success": True,
                "file_path": video_path,
                "thumbnail_path": thumbnail_path,
                "file_size_mb": file_size_mb,
            }

        except Exception as e:
            logger.error(f"Failed to cache video file: {e}")
            return {"success": False, "message": str(e)}

    async def _save_cache_item(self, cache_item: OfflineCacheItem):
        """Save cache item to Redis"""
        try:
            cache_key = f"mobile_cache_item:{cache_item.video_id}"
            cache_data = {
                "video_id": cache_item.video_id,
                "title": cache_item.title,
                "artist_name": cache_item.artist_name,
                "file_path": cache_item.file_path,
                "thumbnail_path": cache_item.thumbnail_path,
                "cache_size_mb": cache_item.cache_size_mb,
                "cached_at": cache_item.cached_at.isoformat(),
                "last_accessed": cache_item.last_accessed.isoformat(),
                "quality": cache_item.quality,
                "expires_at": (
                    cache_item.expires_at.isoformat() if cache_item.expires_at else None
                ),
            }

            await self.redis_client.setex(
                cache_key, 86400 * self.cache_retention_days, json.dumps(cache_data)
            )

            # Add to cache index
            await self.redis_client.sadd("mobile_cache_index", str(cache_item.video_id))

        except Exception as e:
            logger.error(f"Failed to save cache item: {e}")

    async def _get_all_cached_videos(self) -> List[OfflineCacheItem]:
        """Get all cached videos"""
        try:
            cached_video_ids = await self.redis_client.smembers("mobile_cache_index")
            cached_videos = []

            for video_id in cached_video_ids:
                cache_item = await self._get_cached_video(int(video_id))
                if cache_item:
                    cached_videos.append(cache_item)

            return cached_videos

        except Exception as e:
            logger.error(f"Failed to get all cached videos: {e}")
            return []

    async def _get_total_cache_size(self) -> float:
        """Get total cache size in MB"""
        try:
            cached_videos = await self._get_all_cached_videos()
            return sum(item.cache_size_mb for item in cached_videos)

        except Exception as e:
            logger.error(f"Failed to get total cache size: {e}")
            return 0.0

    async def _cleanup_old_cache_items(self):
        """Clean up old cache items to free space"""
        try:
            cached_videos = await self._get_all_cached_videos()

            # Sort by last accessed (oldest first)
            cached_videos.sort(key=lambda x: x.last_accessed)

            # Remove oldest 25% of cached items
            items_to_remove = len(cached_videos) // 4

            for i in range(items_to_remove):
                await self._remove_cached_video(cached_videos[i])

            logger.info(f"Cleaned up {items_to_remove} old cache items")

        except Exception as e:
            logger.error(f"Failed to cleanup old cache items: {e}")

    async def _remove_cached_video(self, cache_item: OfflineCacheItem):
        """Remove cached video"""
        try:
            # Remove files
            if os.path.exists(cache_item.file_path):
                os.remove(cache_item.file_path)
            if os.path.exists(cache_item.thumbnail_path):
                os.remove(cache_item.thumbnail_path)

            # Remove from Redis
            cache_key = f"mobile_cache_item:{cache_item.video_id}"
            await self.redis_client.delete(cache_key)
            await self.redis_client.srem("mobile_cache_index", str(cache_item.video_id))

        except Exception as e:
            logger.error(f"Failed to remove cached video: {e}")

    async def _get_videos_for_strategy(
        self, strategy: OfflineStrategy, user_id: Optional[int], max_videos: int
    ) -> List[int]:
        """Get video IDs based on offline strategy"""
        try:
            video_ids = []

            async with get_async_session() as session:
                if strategy == OfflineStrategy.RECENT_WATCHED:
                    # Get recently watched videos
                    query = (
                        select(Video.id)
                        .order_by(desc(Video.last_watched))
                        .limit(max_videos)
                    )
                    result = await session.execute(query)
                    video_ids = [row[0] for row in result.all()]

                elif strategy == OfflineStrategy.FAVORITES_ONLY:
                    # Would get user favorites - simplified for now
                    query = (
                        select(Video.id)
                        .where(Video.is_music_video == True)
                        .limit(max_videos)
                    )
                    result = await session.execute(query)
                    video_ids = [row[0] for row in result.all()]

                elif strategy == OfflineStrategy.SMART_CACHE:
                    # Intelligent selection based on view count and recency
                    query = (
                        select(Video.id)
                        .where(and_(Video.is_music_video == True, Video.view_count > 0))
                        .order_by(desc(Video.view_count), desc(Video.created_at))
                        .limit(max_videos)
                    )
                    result = await session.execute(query)
                    video_ids = [row[0] for row in result.all()]

                else:
                    # Default to recent videos
                    query = (
                        select(Video.id)
                        .order_by(desc(Video.created_at))
                        .limit(max_videos)
                    )
                    result = await session.execute(query)
                    video_ids = [row[0] for row in result.all()]

            return video_ids

        except Exception as e:
            logger.error(f"Failed to get videos for strategy {strategy}: {e}")
            return []

    async def _get_continue_watching_mobile(
        self, user_id: Optional[int], limit: int
    ) -> List[Dict]:
        """Get continue watching for mobile"""
        # Placeholder - would integrate with watch history service
        return []

    async def _get_favorite_playlists_mobile(
        self, user_id: Optional[int], limit: int
    ) -> List[Dict]:
        """Get favorite playlists for mobile"""
        # Placeholder - would integrate with playlist service
        return []

    async def _get_offline_content_summary(self) -> Dict[str, Any]:
        """Get offline content summary"""
        cached_videos = await self._get_all_cached_videos()
        return {
            "total_videos": len(cached_videos),
            "total_size_mb": sum(item.cache_size_mb for item in cached_videos),
            "last_sync": datetime.now().isoformat(),
        }

    async def _get_mobile_quick_actions(
        self, user_id: Optional[int]
    ) -> List[Dict[str, str]]:
        """Get quick actions for mobile interface"""
        return [
            {"action": "sync_offline", "label": "Sync Offline", "icon": "download"},
            {"action": "clear_cache", "label": "Clear Cache", "icon": "trash"},
            {"action": "search", "label": "Search", "icon": "search"},
            {"action": "playlists", "label": "Playlists", "icon": "playlist"},
        ]

    async def _get_offline_video_cards(self) -> List[MobileVideoCard]:
        """Get offline video cards"""
        try:
            cached_videos = await self._get_all_cached_videos()
            cards = []

            for cached_item in cached_videos:
                card = MobileVideoCard(
                    video_id=cached_item.video_id,
                    title=cached_item.title,
                    artist_name=cached_item.artist_name,
                    duration=0,  # Would need to store duration
                    thumbnail_url=cached_item.thumbnail_path,
                    is_cached=True,
                    cache_size_mb=cached_item.cache_size_mb,
                    quality_available=[cached_item.quality],
                    is_favorite=False,
                    last_watched_position=0,
                )
                cards.append(card)

            return cards

        except Exception as e:
            logger.error(f"Failed to get offline video cards: {e}")
            return []

    async def _update_sync_stats(self, sync_results: Dict[str, Any]):
        """Update sync statistics"""
        try:
            await self.redis_client.setex(
                "last_offline_sync", 86400, datetime.now().isoformat()
            )
            await self.redis_client.setex(
                "last_sync_results", 86400, json.dumps(sync_results)
            )

        except Exception as e:
            logger.error(f"Failed to update sync stats: {e}")


# Global service instance
_mobile_web_service = None


async def get_mobile_web_service(config: Optional[Dict] = None) -> MobileWebService:
    """Get global mobile web service instance"""
    global _mobile_web_service

    if _mobile_web_service is None:
        _mobile_web_service = MobileWebService(config)
        await _mobile_web_service.initialize()

    return _mobile_web_service
