"""
Modern Video Browser Service - Phase 3 Week 30
Consumer-focused video browsing with grid/list views optimized for music videos
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import selectinload

from src.database.async_connection import get_async_session
from src.database.models import Video
from src.services.enhanced_artist_discovery_service import get_enhanced_artist_discovery
from src.services.music_video_detector import get_music_video_detector
from src.services.performance_monitor import get_performance_monitor
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.video_browser")


class ViewMode(Enum):
    """Video browser view modes"""

    GRID_LARGE = "grid_large"  # Large thumbnails, 3-4 per row
    GRID_MEDIUM = "grid_medium"  # Medium thumbnails, 5-6 per row
    GRID_SMALL = "grid_small"  # Small thumbnails, 7-8 per row
    LIST_DETAILED = "list_detailed"  # List with detailed info
    LIST_COMPACT = "list_compact"  # Compact list view


class SortOption(Enum):
    """Video sorting options"""

    RECENTLY_ADDED = "recently_added"
    TITLE_AZ = "title_az"
    TITLE_ZA = "title_za"
    ARTIST_AZ = "artist_az"
    ARTIST_ZA = "artist_za"
    DURATION_SHORT = "duration_short"
    DURATION_LONG = "duration_long"
    FILE_SIZE_SMALL = "file_size_small"
    FILE_SIZE_LARGE = "file_size_large"
    MOST_VIEWED = "most_viewed"
    RECENTLY_WATCHED = "recently_watched"
    DATE_ADDED = "date_added"
    QUALITY_HIGH = "quality_high"


class FilterOption(Enum):
    """Video filtering options"""

    ALL_VIDEOS = "all_videos"
    MUSIC_VIDEOS_ONLY = "music_videos_only"
    NON_MUSIC_VIDEOS = "non_music_videos"
    HIGH_QUALITY = "high_quality"  # 720p+
    MEDIUM_QUALITY = "medium_quality"  # 480p-720p
    LOW_QUALITY = "low_quality"  # <480p
    RECENT_IMPORTS = "recent_imports"  # Last 7 days
    LARGE_FILES = "large_files"  # >100MB
    SMALL_FILES = "small_files"  # <50MB
    WATCHED = "watched"
    UNWATCHED = "unwatched"


@dataclass
class VideoThumbnail:
    """Video thumbnail data for browser display"""

    video_id: int
    title: str
    artist: str
    duration: int
    file_size: int
    quality: str
    thumbnail_path: str
    view_count: int
    last_watched: Optional[datetime]
    date_added: datetime
    is_music_video: bool
    confidence_score: float
    file_path: str


@dataclass
class BrowserResult:
    """Video browser query result"""

    videos: List[VideoThumbnail]
    total_count: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool
    filters_applied: Dict[str, Any]
    sort_option: SortOption
    view_mode: ViewMode


@dataclass
class BrowserPreferences:
    """User browser preferences"""

    default_view_mode: ViewMode = ViewMode.GRID_MEDIUM
    default_sort: SortOption = SortOption.RECENTLY_ADDED
    default_per_page: int = 24
    show_music_videos_only: bool = False
    thumbnail_size: str = "medium"
    show_file_info: bool = True
    show_watch_progress: bool = True
    auto_play_preview: bool = False


class VideoBrowserService:
    """Modern video browser service for music video collections"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.music_video_detector = None
        self.artist_discovery = None
        self.performance_monitor = None

        # Browser configuration
        self.default_thumbnail_sizes = {
            "small": {"width": 160, "height": 90},
            "medium": {"width": 320, "height": 180},
            "large": {"width": 480, "height": 270},
        }

        # View mode configurations
        self.view_configurations = {
            ViewMode.GRID_LARGE: {
                "per_row": 3,
                "thumbnail_size": "large",
                "show_details": True,
            },
            ViewMode.GRID_MEDIUM: {
                "per_row": 4,
                "thumbnail_size": "medium",
                "show_details": True,
            },
            ViewMode.GRID_SMALL: {
                "per_row": 6,
                "thumbnail_size": "small",
                "show_details": False,
            },
            ViewMode.LIST_DETAILED: {
                "per_row": 1,
                "thumbnail_size": "medium",
                "show_details": True,
            },
            ViewMode.LIST_COMPACT: {
                "per_row": 1,
                "thumbnail_size": "small",
                "show_details": False,
            },
        }

        # Performance settings
        self.max_per_page = 100
        self.default_per_page = 24
        self.cache_duration = 300  # 5 minutes

    async def initialize(self):
        """Initialize video browser service"""
        try:
            self.redis_client = await get_redis_client()
            self.music_video_detector = await get_music_video_detector()
            self.artist_discovery = await get_enhanced_artist_discovery()
            self.performance_monitor = await get_performance_monitor()

            logger.info("Video browser service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize video browser service: {e}")
            raise

    async def browse_videos(
        self,
        page: int = 1,
        per_page: int = 24,
        view_mode: ViewMode = ViewMode.GRID_MEDIUM,
        sort_option: SortOption = SortOption.RECENTLY_ADDED,
        filters: Optional[Dict[str, Any]] = None,
        search_query: Optional[str] = None,
    ) -> BrowserResult:
        """Browse videos with specified parameters"""
        try:
            # Validate parameters
            page = max(1, page)
            per_page = min(self.max_per_page, max(1, per_page))
            filters = filters or {}

            logger.info(
                f"Browsing videos: page={page}, per_page={per_page}, sort={sort_option.value}, view={view_mode.value}"
            )

            async with get_async_session() as session:
                # Build base query
                query = select(Video).options(selectinload(Video.artist))

                # Apply filters
                query = await self._apply_filters(query, filters, search_query)

                # Get total count
                count_query = select(func.count(Video.id))
                count_query = await self._apply_filters(
                    count_query, filters, search_query
                )
                total_count = await session.scalar(count_query)

                # Apply sorting
                query = self._apply_sorting(query, sort_option)

                # Apply pagination
                offset = (page - 1) * per_page
                query = query.offset(offset).limit(per_page)

                # Execute query
                result = await session.execute(query)
                videos = result.scalars().all()

                # Convert to thumbnails
                thumbnails = []
                for video in videos:
                    thumbnail = await self._video_to_thumbnail(video)
                    thumbnails.append(thumbnail)

                # Calculate pagination info
                total_pages = (total_count + per_page - 1) // per_page
                has_next = page < total_pages
                has_prev = page > 1

                # Create result
                browser_result = BrowserResult(
                    videos=thumbnails,
                    total_count=total_count,
                    page=page,
                    per_page=per_page,
                    total_pages=total_pages,
                    has_next=has_next,
                    has_prev=has_prev,
                    filters_applied=filters,
                    sort_option=sort_option,
                    view_mode=view_mode,
                )

                # Cache result for performance
                await self._cache_browser_result(browser_result, filters, search_query)

                logger.info(
                    f"Browser query returned {len(thumbnails)} videos out of {total_count} total"
                )

                return browser_result

        except Exception as e:
            logger.error(f"Failed to browse videos: {e}")
            raise

    async def _apply_filters(
        self, query, filters: Dict[str, Any], search_query: Optional[str]
    ):
        """Apply filters to video query"""
        try:
            conditions = []

            # Text search
            if search_query and search_query.strip():
                search_terms = search_query.strip().split()
                for term in search_terms:
                    term_condition = or_(
                        Video.title.ilike(f"%{term}%"),
                        Video.artist_name.ilike(f"%{term}%"),
                        Video.description.ilike(f"%{term}%"),
                    )
                    conditions.append(term_condition)

            # Music video filter
            if filters.get("filter_type") == FilterOption.MUSIC_VIDEOS_ONLY.value:
                conditions.append(Video.is_music_video == True)
            elif filters.get("filter_type") == FilterOption.NON_MUSIC_VIDEOS.value:
                conditions.append(Video.is_music_video == False)

            # Quality filters
            if filters.get("filter_type") == FilterOption.HIGH_QUALITY.value:
                conditions.append(Video.height >= 720)
            elif filters.get("filter_type") == FilterOption.MEDIUM_QUALITY.value:
                conditions.append(and_(Video.height >= 480, Video.height < 720))
            elif filters.get("filter_type") == FilterOption.LOW_QUALITY.value:
                conditions.append(Video.height < 480)

            # File size filters
            if filters.get("filter_type") == FilterOption.LARGE_FILES.value:
                conditions.append(Video.file_size > 100 * 1024 * 1024)  # >100MB
            elif filters.get("filter_type") == FilterOption.SMALL_FILES.value:
                conditions.append(Video.file_size < 50 * 1024 * 1024)  # <50MB

            # Recent imports filter
            if filters.get("filter_type") == FilterOption.RECENT_IMPORTS.value:
                week_ago = datetime.now() - timedelta(days=7)
                conditions.append(Video.created_at >= week_ago)

            # Watch status filters
            if filters.get("filter_type") == FilterOption.WATCHED.value:
                conditions.append(Video.view_count > 0)
            elif filters.get("filter_type") == FilterOption.UNWATCHED.value:
                conditions.append(Video.view_count == 0)

            # Artist filter
            if filters.get("artist_id"):
                conditions.append(Video.artist_id == filters["artist_id"])

            # Duration filters
            if filters.get("min_duration"):
                conditions.append(Video.duration >= filters["min_duration"])
            if filters.get("max_duration"):
                conditions.append(Video.duration <= filters["max_duration"])

            # Date range filters
            if filters.get("date_from"):
                try:
                    date_from = datetime.fromisoformat(filters["date_from"])
                    conditions.append(Video.created_at >= date_from)
                except:
                    pass

            if filters.get("date_to"):
                try:
                    date_to = datetime.fromisoformat(filters["date_to"])
                    conditions.append(Video.created_at <= date_to)
                except:
                    pass

            # Apply all conditions
            if conditions:
                query = query.where(and_(*conditions))

            return query

        except Exception as e:
            logger.error(f"Failed to apply filters: {e}")
            return query

    def _apply_sorting(self, query, sort_option: SortOption):
        """Apply sorting to video query"""
        try:
            if sort_option == SortOption.RECENTLY_ADDED:
                return query.order_by(desc(Video.created_at))
            elif sort_option == SortOption.TITLE_AZ:
                return query.order_by(asc(Video.title))
            elif sort_option == SortOption.TITLE_ZA:
                return query.order_by(desc(Video.title))
            elif sort_option == SortOption.ARTIST_AZ:
                return query.order_by(asc(Video.artist_name))
            elif sort_option == SortOption.ARTIST_ZA:
                return query.order_by(desc(Video.artist_name))
            elif sort_option == SortOption.DURATION_SHORT:
                return query.order_by(asc(Video.duration))
            elif sort_option == SortOption.DURATION_LONG:
                return query.order_by(desc(Video.duration))
            elif sort_option == SortOption.FILE_SIZE_SMALL:
                return query.order_by(asc(Video.file_size))
            elif sort_option == SortOption.FILE_SIZE_LARGE:
                return query.order_by(desc(Video.file_size))
            elif sort_option == SortOption.MOST_VIEWED:
                return query.order_by(desc(Video.view_count))
            elif sort_option == SortOption.RECENTLY_WATCHED:
                return query.order_by(desc(Video.last_watched))
            elif sort_option == SortOption.DATE_ADDED:
                return query.order_by(desc(Video.created_at))
            elif sort_option == SortOption.QUALITY_HIGH:
                return query.order_by(desc(Video.height), desc(Video.bitrate))
            else:
                return query.order_by(desc(Video.created_at))

        except Exception as e:
            logger.error(f"Failed to apply sorting: {e}")
            return query.order_by(desc(Video.created_at))

    async def _video_to_thumbnail(self, video: Video) -> VideoThumbnail:
        """Convert video model to thumbnail data"""
        try:
            # Get or generate thumbnail path
            thumbnail_path = await self._get_video_thumbnail_path(video.id)

            # Determine artist name
            artist_name = video.artist_name or "Unknown Artist"
            if video.artist:
                artist_name = video.artist.name

            return VideoThumbnail(
                video_id=video.id,
                title=video.title or "Unknown Title",
                artist=artist_name,
                duration=video.duration or 0,
                file_size=video.file_size or 0,
                quality=self._format_quality_display(video.width, video.height),
                thumbnail_path=thumbnail_path,
                view_count=video.view_count or 0,
                last_watched=video.last_watched,
                date_added=video.created_at or datetime.now(),
                is_music_video=video.is_music_video or False,
                confidence_score=getattr(video, "music_video_confidence", 0.0),
                file_path=video.file_path or "",
            )

        except Exception as e:
            logger.error(f"Failed to convert video to thumbnail: {e}")
            # Return basic thumbnail data
            return VideoThumbnail(
                video_id=video.id,
                title=video.title or "Unknown Title",
                artist=video.artist_name or "Unknown Artist",
                duration=video.duration or 0,
                file_size=video.file_size or 0,
                quality="Unknown",
                thumbnail_path="",
                view_count=video.view_count or 0,
                last_watched=video.last_watched,
                date_added=video.created_at or datetime.now(),
                is_music_video=video.is_music_video or False,
                confidence_score=0.0,
                file_path=video.file_path or "",
            )

    async def _get_video_thumbnail_path(self, video_id: int) -> str:
        """Get or generate thumbnail path for video"""
        try:
            # Check if thumbnail exists in cache
            cache_key = f"video_thumbnail:{video_id}"
            cached_path = await self.redis_client.get(cache_key)

            if cached_path:
                return cached_path

            # Generate thumbnail path
            thumbnail_dir = "/data/thumbnails"
            thumbnail_path = f"{thumbnail_dir}/video_{video_id}_medium.jpg"

            # Check if thumbnail file exists
            if os.path.exists(thumbnail_path):
                # Cache the path
                await self.redis_client.setex(cache_key, 3600, thumbnail_path)
                return thumbnail_path

            # Return placeholder or generate thumbnail
            return f"/api/thumbnails/video/{video_id}"

        except Exception as e:
            logger.error(f"Failed to get thumbnail path for video {video_id}: {e}")
            return f"/api/thumbnails/video/{video_id}"

    def _format_quality_display(
        self, width: Optional[int], height: Optional[int]
    ) -> str:
        """Format video quality for display"""
        try:
            if not height:
                return "Unknown"

            if height >= 2160:
                return "4K"
            elif height >= 1440:
                return "1440p"
            elif height >= 1080:
                return "1080p"
            elif height >= 720:
                return "720p HD"
            elif height >= 480:
                return "480p"
            elif height >= 360:
                return "360p"
            else:
                return f"{height}p"

        except:
            return "Unknown"

    async def get_browser_statistics(self) -> Dict[str, Any]:
        """Get video browser statistics"""
        try:
            async with get_async_session() as session:
                # Total videos
                total_videos = await session.scalar(select(func.count(Video.id)))

                # Music videos
                music_videos = await session.scalar(
                    select(func.count(Video.id)).where(Video.is_music_video == True)
                )

                # Quality distribution
                quality_stats = {}
                quality_result = await session.execute(
                    select(Video.height, func.count(Video.id))
                    .group_by(Video.height)
                    .order_by(desc(func.count(Video.id)))
                )

                for height, count in quality_result:
                    quality_display = self._format_quality_display(None, height)
                    quality_stats[quality_display] = count

                # Recently added (last 7 days)
                week_ago = datetime.now() - timedelta(days=7)
                recent_videos = await session.scalar(
                    select(func.count(Video.id)).where(Video.created_at >= week_ago)
                )

                # File size statistics
                size_stats = await session.execute(
                    select(
                        func.avg(Video.file_size).label("avg_size"),
                        func.sum(Video.file_size).label("total_size"),
                        func.min(Video.file_size).label("min_size"),
                        func.max(Video.file_size).label("max_size"),
                    )
                )
                size_row = size_stats.first()

                return {
                    "total_videos": total_videos or 0,
                    "music_videos": music_videos or 0,
                    "non_music_videos": (total_videos or 0) - (music_videos or 0),
                    "music_video_percentage": round(
                        (music_videos or 0) / max(total_videos or 1, 1) * 100, 1
                    ),
                    "recent_videos_week": recent_videos or 0,
                    "quality_distribution": quality_stats,
                    "file_size_stats": {
                        "average_mb": round(
                            (size_row.avg_size or 0) / (1024 * 1024), 1
                        ),
                        "total_gb": round(
                            (size_row.total_size or 0) / (1024 * 1024 * 1024), 2
                        ),
                        "smallest_mb": round(
                            (size_row.min_size or 0) / (1024 * 1024), 1
                        ),
                        "largest_mb": round(
                            (size_row.max_size or 0) / (1024 * 1024), 1
                        ),
                    },
                    "last_updated": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Failed to get browser statistics: {e}")
            return {
                "total_videos": 0,
                "music_videos": 0,
                "non_music_videos": 0,
                "music_video_percentage": 0,
                "recent_videos_week": 0,
                "quality_distribution": {},
                "file_size_stats": {},
                "last_updated": datetime.now().isoformat(),
            }

    async def get_quick_filters(self) -> Dict[str, Any]:
        """Get quick filter options with counts"""
        try:
            async with get_async_session() as session:
                filters = {}

                # Music video filter
                music_count = await session.scalar(
                    select(func.count(Video.id)).where(Video.is_music_video == True)
                )
                filters["music_videos"] = {
                    "label": "Music Videos Only",
                    "count": music_count or 0,
                    "filter_type": FilterOption.MUSIC_VIDEOS_ONLY.value,
                }

                # Quality filters
                hq_count = await session.scalar(
                    select(func.count(Video.id)).where(Video.height >= 720)
                )
                filters["high_quality"] = {
                    "label": "HD Quality (720p+)",
                    "count": hq_count or 0,
                    "filter_type": FilterOption.HIGH_QUALITY.value,
                }

                # Recent imports
                week_ago = datetime.now() - timedelta(days=7)
                recent_count = await session.scalar(
                    select(func.count(Video.id)).where(Video.created_at >= week_ago)
                )
                filters["recent_imports"] = {
                    "label": "Added This Week",
                    "count": recent_count or 0,
                    "filter_type": FilterOption.RECENT_IMPORTS.value,
                }

                # Unwatched videos
                unwatched_count = await session.scalar(
                    select(func.count(Video.id)).where(Video.view_count == 0)
                )
                filters["unwatched"] = {
                    "label": "Never Watched",
                    "count": unwatched_count or 0,
                    "filter_type": FilterOption.UNWATCHED.value,
                }

                # Large files
                large_count = await session.scalar(
                    select(func.count(Video.id)).where(
                        Video.file_size > 100 * 1024 * 1024
                    )
                )
                filters["large_files"] = {
                    "label": "Large Files (>100MB)",
                    "count": large_count or 0,
                    "filter_type": FilterOption.LARGE_FILES.value,
                }

                return filters

        except Exception as e:
            logger.error(f"Failed to get quick filters: {e}")
            return {}

    async def save_user_preferences(
        self, user_id: str, preferences: BrowserPreferences
    ):
        """Save user browser preferences"""
        try:
            cache_key = f"browser_preferences:{user_id}"
            prefs_dict = {
                "default_view_mode": preferences.default_view_mode.value,
                "default_sort": preferences.default_sort.value,
                "default_per_page": preferences.default_per_page,
                "show_music_videos_only": preferences.show_music_videos_only,
                "thumbnail_size": preferences.thumbnail_size,
                "show_file_info": preferences.show_file_info,
                "show_watch_progress": preferences.show_watch_progress,
                "auto_play_preview": preferences.auto_play_preview,
                "updated_at": datetime.now().isoformat(),
            }

            await self.redis_client.setex(cache_key, 86400 * 30, json.dumps(prefs_dict))
            logger.info(f"Saved browser preferences for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to save browser preferences: {e}")

    async def get_user_preferences(self, user_id: str) -> BrowserPreferences:
        """Get user browser preferences"""
        try:
            cache_key = f"browser_preferences:{user_id}"
            cached_prefs = await self.redis_client.get(cache_key)

            if cached_prefs:
                prefs_dict = json.loads(cached_prefs)
                return BrowserPreferences(
                    default_view_mode=ViewMode(
                        prefs_dict.get("default_view_mode", ViewMode.GRID_MEDIUM.value)
                    ),
                    default_sort=SortOption(
                        prefs_dict.get("default_sort", SortOption.RECENTLY_ADDED.value)
                    ),
                    default_per_page=prefs_dict.get("default_per_page", 24),
                    show_music_videos_only=prefs_dict.get(
                        "show_music_videos_only", False
                    ),
                    thumbnail_size=prefs_dict.get("thumbnail_size", "medium"),
                    show_file_info=prefs_dict.get("show_file_info", True),
                    show_watch_progress=prefs_dict.get("show_watch_progress", True),
                    auto_play_preview=prefs_dict.get("auto_play_preview", False),
                )

            return BrowserPreferences()  # Return defaults

        except Exception as e:
            logger.error(f"Failed to get browser preferences: {e}")
            return BrowserPreferences()

    async def _cache_browser_result(
        self, result: BrowserResult, filters: Dict, search_query: Optional[str]
    ):
        """Cache browser result for performance"""
        try:
            # Create cache key from parameters
            cache_params = {
                "page": result.page,
                "per_page": result.per_page,
                "sort": result.sort_option.value,
                "view": result.view_mode.value,
                "filters": filters,
                "search": search_query or "",
            }
            cache_key = f"browser_result:{hash(str(cache_params))}"

            # Cache lightweight version (no full video data)
            cache_data = {
                "total_count": result.total_count,
                "total_pages": result.total_pages,
                "has_next": result.has_next,
                "has_prev": result.has_prev,
                "video_ids": [v.video_id for v in result.videos],
                "cached_at": datetime.now().isoformat(),
            }

            await self.redis_client.setex(
                cache_key, self.cache_duration, json.dumps(cache_data)
            )

        except Exception as e:
            logger.error(f"Failed to cache browser result: {e}")


# Global service instance
_video_browser_service = None


async def get_video_browser_service(
    config: Optional[Dict] = None,
) -> VideoBrowserService:
    """Get global video browser service instance"""
    global _video_browser_service

    if _video_browser_service is None:
        _video_browser_service = VideoBrowserService(config)
        await _video_browser_service.initialize()

    return _video_browser_service
