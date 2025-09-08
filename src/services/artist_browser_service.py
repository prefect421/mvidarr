"""
Artist & Album Browser Service - Phase 3 Week 30
Consumer-focused artist and album browsing with cover art and smart grouping
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
from pathlib import Path
import aiofiles
from dataclasses import dataclass
import hashlib
import aiohttp

from src.utils.logger import get_logger
from src.services.redis_service import get_redis_client
from src.services.music_video_detector import get_music_video_detector
from src.services.enhanced_artist_discovery_service import get_enhanced_artist_discovery
from src.database import get_async_session
from src.models.video import Video
from src.models.artist import Artist
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, distinct
from sqlalchemy.orm import selectinload

logger = get_logger("mvidarr.artist_browser")

class ArtistSortOption(Enum):
    """Artist sorting options"""
    NAME_AZ = "name_az"
    NAME_ZA = "name_za"
    VIDEO_COUNT_HIGH = "video_count_high"
    VIDEO_COUNT_LOW = "video_count_low"
    RECENTLY_ADDED = "recently_added"
    MOST_VIEWED = "most_viewed"
    ALPHABETICAL = "alphabetical"

class AlbumSortOption(Enum):
    """Album sorting options"""
    TITLE_AZ = "title_az"
    TITLE_ZA = "title_za"
    YEAR_NEW = "year_new"
    YEAR_OLD = "year_old"
    TRACK_COUNT = "track_count"
    RECENTLY_ADDED = "recently_added"

class BrowseMode(Enum):
    """Browser display modes"""
    ARTIST_GRID = "artist_grid"         # Grid of artist cards with cover art
    ARTIST_LIST = "artist_list"         # List view of artists
    ALBUM_GRID = "album_grid"           # Grid of album covers
    ALBUM_LIST = "album_list"           # List view of albums
    COMBINED_VIEW = "combined_view"     # Artists and albums combined

@dataclass
class ArtistCard:
    """Artist card data for browser display"""
    artist_id: int
    name: str
    video_count: int
    total_duration: int
    cover_art_path: Optional[str]
    genres: List[str]
    first_video_date: Optional[datetime]
    last_video_date: Optional[datetime]
    total_views: int
    music_video_count: int
    top_videos: List[Dict[str, Any]]  # Top 3 videos
    description: Optional[str]
    external_urls: Dict[str, str]  # Spotify, YouTube, etc.

@dataclass
class AlbumCard:
    """Album card data for browser display"""
    album_id: str  # Generated ID
    title: str
    artist_name: str
    artist_id: int
    track_count: int
    total_duration: int
    year: Optional[int]
    cover_art_path: Optional[str]
    genres: List[str]
    tracks: List[Dict[str, Any]]
    release_date: Optional[datetime]
    total_views: int

@dataclass
class ArtistProfile:
    """Detailed artist profile"""
    artist_id: int
    name: str
    description: Optional[str]
    cover_art_path: Optional[str]
    banner_art_path: Optional[str]
    genres: List[str]
    video_count: int
    total_duration: int
    total_views: int
    music_video_count: int
    first_video_date: Optional[datetime]
    last_video_date: Optional[datetime]
    top_videos: List[Dict[str, Any]]
    recent_videos: List[Dict[str, Any]]
    albums: List[AlbumCard]
    similar_artists: List[Dict[str, Any]]
    external_urls: Dict[str, str]
    statistics: Dict[str, Any]

class ArtistBrowserService:
    """Artist and album browsing service for music video collections"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.music_video_detector = None
        self.artist_discovery = None
        
        # Art and image settings
        self.cover_art_sizes = {
            'thumbnail': {'width': 150, 'height': 150},
            'medium': {'width': 300, 'height': 300},
            'large': {'width': 500, 'height': 500}
        }
        
        # Cache settings
        self.cache_duration = 3600  # 1 hour
        self.cover_art_cache_duration = 86400 * 7  # 1 week
        
        # External API settings for cover art
        self.enable_external_art = True
        self.art_sources = ['last.fm', 'musicbrainz', 'spotify']
        
    async def initialize(self):
        """Initialize artist browser service"""
        try:
            self.redis_client = await get_redis_client()
            self.music_video_detector = await get_music_video_detector()
            self.artist_discovery = await get_enhanced_artist_discovery()
            
            logger.info("Artist browser service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize artist browser service: {e}")
            raise
    
    async def browse_artists(
        self,
        page: int = 1,
        per_page: int = 24,
        sort_option: ArtistSortOption = ArtistSortOption.NAME_AZ,
        mode: BrowseMode = BrowseMode.ARTIST_GRID,
        filters: Optional[Dict[str, Any]] = None,
        search_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Browse artists with specified parameters"""
        try:
            # Validate parameters
            page = max(1, page)
            per_page = min(100, max(1, per_page))
            filters = filters or {}
            
            logger.info(f"Browsing artists: page={page}, per_page={per_page}, sort={sort_option.value}")
            
            async with get_async_session() as session:
                # Build base query with video counts and statistics
                base_query = select(
                    Artist.id,
                    Artist.name,
                    Artist.description,
                    Artist.spotify_url,
                    Artist.youtube_url,
                    func.count(Video.id).label('video_count'),
                    func.sum(Video.duration).label('total_duration'),
                    func.sum(Video.view_count).label('total_views'),
                    func.count(Video.id).filter(Video.is_music_video == True).label('music_video_count'),
                    func.min(Video.created_at).label('first_video_date'),
                    func.max(Video.created_at).label('last_video_date')
                ).select_from(
                    Artist
                ).outerjoin(Video).group_by(Artist.id, Artist.name, Artist.description, Artist.spotify_url, Artist.youtube_url)
                
                # Apply search filter
                if search_query and search_query.strip():
                    base_query = base_query.having(Artist.name.ilike(f'%{search_query.strip()}%'))
                
                # Apply additional filters
                if filters.get('has_videos_only', True):
                    base_query = base_query.having(func.count(Video.id) > 0)
                
                if filters.get('music_videos_only'):
                    base_query = base_query.having(func.count(Video.id).filter(Video.is_music_video == True) > 0)
                
                if filters.get('min_video_count'):
                    base_query = base_query.having(func.count(Video.id) >= filters['min_video_count'])
                
                # Get total count
                count_result = await session.execute(base_query)
                total_count = len(count_result.all())
                
                # Apply sorting
                base_query = self._apply_artist_sorting(base_query, sort_option)
                
                # Apply pagination
                offset = (page - 1) * per_page
                base_query = base_query.offset(offset).limit(per_page)
                
                # Execute query
                result = await session.execute(base_query)
                artist_rows = result.all()
                
                # Convert to artist cards
                artist_cards = []
                for row in artist_rows:
                    artist_card = await self._create_artist_card(session, row)
                    artist_cards.append(artist_card)
                
                # Calculate pagination info
                total_pages = (total_count + per_page - 1) // per_page
                has_next = page < total_pages
                has_prev = page > 1
                
                return {
                    'artists': [card.__dict__ for card in artist_cards],
                    'total_count': total_count,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'has_next': has_next,
                    'has_prev': has_prev,
                    'sort_option': sort_option.value,
                    'browse_mode': mode.value,
                    'filters_applied': filters
                }
                
        except Exception as e:
            logger.error(f"Failed to browse artists: {e}")
            raise
    
    async def browse_albums(
        self,
        page: int = 1,
        per_page: int = 24,
        sort_option: AlbumSortOption = AlbumSortOption.TITLE_AZ,
        mode: BrowseMode = BrowseMode.ALBUM_GRID,
        filters: Optional[Dict[str, Any]] = None,
        search_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Browse albums (grouped videos) with specified parameters"""
        try:
            logger.info(f"Browsing albums: page={page}, per_page={per_page}, sort={sort_option.value}")
            
            # Get album-like groupings from videos
            albums = await self._get_album_groupings(search_query, filters)
            
            # Apply sorting
            albums = self._sort_albums(albums, sort_option)
            
            # Apply pagination
            total_count = len(albums)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_albums = albums[start_idx:end_idx]
            
            # Add cover art for each album
            for album in paginated_albums:
                album.cover_art_path = await self._get_album_cover_art(album)
            
            # Calculate pagination info
            total_pages = (total_count + per_page - 1) // per_page
            has_next = page < total_pages
            has_prev = page > 1
            
            return {
                'albums': [album.__dict__ for album in paginated_albums],
                'total_count': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev,
                'sort_option': sort_option.value,
                'browse_mode': mode.value,
                'filters_applied': filters or {}
            }
            
        except Exception as e:
            logger.error(f"Failed to browse albums: {e}")
            raise
    
    async def get_artist_profile(self, artist_id: int) -> Optional[ArtistProfile]:
        """Get detailed artist profile"""
        try:
            # Check cache first
            cache_key = f"artist_profile:{artist_id}"
            cached_profile = await self.redis_client.get(cache_key)
            
            if cached_profile:
                profile_data = json.loads(cached_profile)
                return ArtistProfile(**profile_data)
            
            async with get_async_session() as session:
                # Get artist with statistics
                artist_query = select(
                    Artist.id,
                    Artist.name,
                    Artist.description,
                    Artist.spotify_url,
                    Artist.youtube_url,
                    func.count(Video.id).label('video_count'),
                    func.sum(Video.duration).label('total_duration'),
                    func.sum(Video.view_count).label('total_views'),
                    func.count(Video.id).filter(Video.is_music_video == True).label('music_video_count'),
                    func.min(Video.created_at).label('first_video_date'),
                    func.max(Video.created_at).label('last_video_date')
                ).select_from(Artist).outerjoin(Video).where(Artist.id == artist_id).group_by(
                    Artist.id, Artist.name, Artist.description, Artist.spotify_url, Artist.youtube_url
                )
                
                result = await session.execute(artist_query)
                artist_row = result.first()
                
                if not artist_row:
                    return None
                
                # Get artist's videos
                videos_query = select(Video).where(Video.artist_id == artist_id).options(selectinload(Video.artist))
                videos_result = await session.execute(videos_query)
                videos = videos_result.scalars().all()
                
                # Get top videos (most viewed)
                top_videos = sorted(videos, key=lambda v: v.view_count or 0, reverse=True)[:5]
                recent_videos = sorted(videos, key=lambda v: v.created_at or datetime.min, reverse=True)[:5]
                
                # Generate album groupings for this artist
                artist_albums = await self._get_artist_albums(artist_id, videos)
                
                # Get cover art
                cover_art_path = await self._get_artist_cover_art(artist_row.name)
                banner_art_path = await self._get_artist_banner_art(artist_row.name)
                
                # Detect genres from videos
                genres = await self._detect_artist_genres(videos)
                
                # Get similar artists
                similar_artists = await self._find_similar_artists(artist_id, genres)
                
                # Create profile
                profile = ArtistProfile(
                    artist_id=artist_row.id,
                    name=artist_row.name,
                    description=artist_row.description,
                    cover_art_path=cover_art_path,
                    banner_art_path=banner_art_path,
                    genres=genres,
                    video_count=artist_row.video_count or 0,
                    total_duration=artist_row.total_duration or 0,
                    total_views=artist_row.total_views or 0,
                    music_video_count=artist_row.music_video_count or 0,
                    first_video_date=artist_row.first_video_date,
                    last_video_date=artist_row.last_video_date,
                    top_videos=[self._video_to_dict(v) for v in top_videos],
                    recent_videos=[self._video_to_dict(v) for v in recent_videos],
                    albums=[album.__dict__ for album in artist_albums],
                    similar_artists=similar_artists,
                    external_urls={
                        'spotify': artist_row.spotify_url or '',
                        'youtube': artist_row.youtube_url or ''
                    },
                    statistics={
                        'avg_video_duration': (artist_row.total_duration or 0) // max(artist_row.video_count or 1, 1),
                        'avg_views_per_video': (artist_row.total_views or 0) // max(artist_row.video_count or 1, 1),
                        'music_video_percentage': round((artist_row.music_video_count or 0) / max(artist_row.video_count or 1, 1) * 100, 1),
                        'active_period_days': (artist_row.last_video_date - artist_row.first_video_date).days if artist_row.first_video_date and artist_row.last_video_date else 0
                    }
                )
                
                # Cache the profile
                await self.redis_client.setex(cache_key, self.cache_duration, json.dumps(profile.__dict__, default=str))
                
                return profile
                
        except Exception as e:
            logger.error(f"Failed to get artist profile for {artist_id}: {e}")
            return None
    
    def _apply_artist_sorting(self, query, sort_option: ArtistSortOption):
        """Apply sorting to artist query"""
        try:
            if sort_option == ArtistSortOption.NAME_AZ:
                return query.order_by(asc(Artist.name))
            elif sort_option == ArtistSortOption.NAME_ZA:
                return query.order_by(desc(Artist.name))
            elif sort_option == ArtistSortOption.VIDEO_COUNT_HIGH:
                return query.order_by(desc(func.count(Video.id)))
            elif sort_option == ArtistSortOption.VIDEO_COUNT_LOW:
                return query.order_by(asc(func.count(Video.id)))
            elif sort_option == ArtistSortOption.RECENTLY_ADDED:
                return query.order_by(desc(func.max(Video.created_at)))
            elif sort_option == ArtistSortOption.MOST_VIEWED:
                return query.order_by(desc(func.sum(Video.view_count)))
            elif sort_option == ArtistSortOption.ALPHABETICAL:
                return query.order_by(asc(Artist.name))
            else:
                return query.order_by(asc(Artist.name))
                
        except Exception as e:
            logger.error(f"Failed to apply artist sorting: {e}")
            return query.order_by(asc(Artist.name))
    
    def _sort_albums(self, albums: List[AlbumCard], sort_option: AlbumSortOption) -> List[AlbumCard]:
        """Sort albums by specified option"""
        try:
            if sort_option == AlbumSortOption.TITLE_AZ:
                return sorted(albums, key=lambda a: a.title.lower())
            elif sort_option == AlbumSortOption.TITLE_ZA:
                return sorted(albums, key=lambda a: a.title.lower(), reverse=True)
            elif sort_option == AlbumSortOption.YEAR_NEW:
                return sorted(albums, key=lambda a: a.year or 0, reverse=True)
            elif sort_option == AlbumSortOption.YEAR_OLD:
                return sorted(albums, key=lambda a: a.year or 9999)
            elif sort_option == AlbumSortOption.TRACK_COUNT:
                return sorted(albums, key=lambda a: a.track_count, reverse=True)
            elif sort_option == AlbumSortOption.RECENTLY_ADDED:
                return sorted(albums, key=lambda a: a.release_date or datetime.min, reverse=True)
            else:
                return sorted(albums, key=lambda a: a.title.lower())
                
        except Exception as e:
            logger.error(f"Failed to sort albums: {e}")
            return albums
    
    async def _create_artist_card(self, session: AsyncSession, artist_row) -> ArtistCard:
        """Create artist card from database row"""
        try:
            # Get top videos for this artist
            top_videos_query = select(Video).where(
                Video.artist_id == artist_row.id
            ).order_by(desc(Video.view_count)).limit(3)
            
            top_videos_result = await session.execute(top_videos_query)
            top_videos = top_videos_result.scalars().all()
            
            # Get cover art
            cover_art_path = await self._get_artist_cover_art(artist_row.name)
            
            # Detect genres (simplified - could be enhanced)
            genres = await self._detect_simple_genres(artist_row.name)
            
            return ArtistCard(
                artist_id=artist_row.id,
                name=artist_row.name,
                video_count=artist_row.video_count or 0,
                total_duration=artist_row.total_duration or 0,
                cover_art_path=cover_art_path,
                genres=genres,
                first_video_date=artist_row.first_video_date,
                last_video_date=artist_row.last_video_date,
                total_views=artist_row.total_views or 0,
                music_video_count=artist_row.music_video_count or 0,
                top_videos=[self._video_to_dict(v) for v in top_videos],
                description=artist_row.description,
                external_urls={
                    'spotify': artist_row.spotify_url or '',
                    'youtube': artist_row.youtube_url or ''
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to create artist card: {e}")
            # Return basic card
            return ArtistCard(
                artist_id=artist_row.id,
                name=artist_row.name,
                video_count=artist_row.video_count or 0,
                total_duration=artist_row.total_duration or 0,
                cover_art_path=None,
                genres=[],
                first_video_date=artist_row.first_video_date,
                last_video_date=artist_row.last_video_date,
                total_views=artist_row.total_views or 0,
                music_video_count=artist_row.music_video_count or 0,
                top_videos=[],
                description=artist_row.description,
                external_urls={}
            )
    
    async def _get_album_groupings(self, search_query: Optional[str], filters: Optional[Dict]) -> List[AlbumCard]:
        """Create album-like groupings from video collection"""
        try:
            # This is a simplified implementation - in a real system, you'd want
            # more sophisticated album detection based on metadata, folder structure, etc.
            
            albums = []
            
            async with get_async_session() as session:
                # Group videos by artist and try to detect album-like collections
                artists_query = select(Artist.id, Artist.name).where(Artist.id.in_(
                    select(Video.artist_id).where(Video.artist_id.isnot(None))
                ))
                
                if search_query:
                    artists_query = artists_query.where(Artist.name.ilike(f'%{search_query}%'))
                
                artists_result = await session.execute(artists_query)
                artists = artists_result.all()
                
                for artist_row in artists:
                    artist_albums = await self._detect_artist_albums(session, artist_row.id, artist_row.name)
                    albums.extend(artist_albums)
            
            return albums
            
        except Exception as e:
            logger.error(f"Failed to get album groupings: {e}")
            return []
    
    async def _detect_artist_albums(self, session: AsyncSession, artist_id: int, artist_name: str) -> List[AlbumCard]:
        """Detect album-like groupings for an artist"""
        try:
            albums = []
            
            # Get all videos for this artist
            videos_query = select(Video).where(Video.artist_id == artist_id)
            videos_result = await session.execute(videos_query)
            videos = videos_result.scalars().all()
            
            if len(videos) < 3:  # Need at least 3 videos to form an "album"
                return albums
            
            # Simple album detection based on video titles and dates
            # Group videos by similar patterns in titles or by date ranges
            
            # Method 1: Group by date ranges (videos added within 30 days of each other)
            sorted_videos = sorted(videos, key=lambda v: v.created_at or datetime.min)
            
            current_album_videos = [sorted_videos[0]] if sorted_videos else []
            album_counter = 1
            
            for video in sorted_videos[1:]:
                if current_album_videos:
                    last_video_date = current_album_videos[-1].created_at
                    current_video_date = video.created_at
                    
                    if (last_video_date and current_video_date and 
                        (current_video_date - last_video_date).days <= 30):
                        current_album_videos.append(video)
                    else:
                        # Create album from current group if it has enough videos
                        if len(current_album_videos) >= 3:
                            album = await self._create_album_card(
                                artist_id, artist_name, current_album_videos, album_counter
                            )
                            albums.append(album)
                            album_counter += 1
                        
                        current_album_videos = [video]
            
            # Don't forget the last group
            if len(current_album_videos) >= 3:
                album = await self._create_album_card(
                    artist_id, artist_name, current_album_videos, album_counter
                )
                albums.append(album)
            
            return albums
            
        except Exception as e:
            logger.error(f"Failed to detect artist albums for {artist_name}: {e}")
            return []
    
    async def _create_album_card(self, artist_id: int, artist_name: str, videos: List[Video], album_num: int) -> AlbumCard:
        """Create album card from grouped videos"""
        try:
            # Generate album title
            if len(videos) > 1:
                first_date = min(v.created_at for v in videos if v.created_at)
                album_title = f"{artist_name} Collection {album_num}"
                if first_date:
                    album_title = f"{artist_name} - {first_date.strftime('%Y')} Collection"
            else:
                album_title = f"{artist_name} Singles"
            
            # Calculate statistics
            total_duration = sum(v.duration or 0 for v in videos)
            total_views = sum(v.view_count or 0 for v in videos)
            
            # Get year from videos
            years = [v.created_at.year for v in videos if v.created_at]
            year = max(years) if years else None
            
            # Generate album ID
            album_id = f"album_{hashlib.md5(f'{artist_id}_{album_num}'.encode()).hexdigest()[:12]}"
            
            return AlbumCard(
                album_id=album_id,
                title=album_title,
                artist_name=artist_name,
                artist_id=artist_id,
                track_count=len(videos),
                total_duration=total_duration,
                year=year,
                cover_art_path=None,  # Will be populated later
                genres=[],  # Could be detected from video metadata
                tracks=[self._video_to_dict(v) for v in videos],
                release_date=min(v.created_at for v in videos if v.created_at) if videos else None,
                total_views=total_views
            )
            
        except Exception as e:
            logger.error(f"Failed to create album card: {e}")
            return AlbumCard(
                album_id=f"error_{album_num}",
                title=f"{artist_name} Collection",
                artist_name=artist_name,
                artist_id=artist_id,
                track_count=len(videos),
                total_duration=0,
                year=None,
                cover_art_path=None,
                genres=[],
                tracks=[],
                release_date=None,
                total_views=0
            )
    
    async def _get_artist_cover_art(self, artist_name: str) -> Optional[str]:
        """Get or generate cover art for artist"""
        try:
            # Check cache first
            cache_key = f"artist_cover_art:{hashlib.md5(artist_name.encode()).hexdigest()}"
            cached_path = await self.redis_client.get(cache_key)
            
            if cached_path:
                return cached_path
            
            # Check if cover art exists locally
            cover_art_dir = "/data/cover_art/artists"
            os.makedirs(cover_art_dir, exist_ok=True)
            
            safe_name = "".join(c for c in artist_name if c.isalnum() or c in (' ', '-', '_')).strip()
            local_path = f"{cover_art_dir}/{safe_name}.jpg"
            
            if os.path.exists(local_path):
                await self.redis_client.setex(cache_key, self.cover_art_cache_duration, local_path)
                return local_path
            
            # Try to fetch from external sources (placeholder implementation)
            if self.enable_external_art:
                external_path = await self._fetch_external_cover_art(artist_name, "artist")
                if external_path:
                    await self.redis_client.setex(cache_key, self.cover_art_cache_duration, external_path)
                    return external_path
            
            # Return placeholder
            placeholder_path = "/static/images/default_artist_cover.jpg"
            await self.redis_client.setex(cache_key, self.cover_art_cache_duration, placeholder_path)
            return placeholder_path
            
        except Exception as e:
            logger.error(f"Failed to get cover art for artist {artist_name}: {e}")
            return "/static/images/default_artist_cover.jpg"
    
    async def _get_album_cover_art(self, album: AlbumCard) -> Optional[str]:
        """Get or generate cover art for album"""
        try:
            # Use first track's thumbnail or artist cover art
            if album.tracks and len(album.tracks) > 0:
                # Try to use video thumbnail
                first_track = album.tracks[0]
                thumbnail_path = f"/data/thumbnails/video_{first_track.get('id', 0)}_medium.jpg"
                if os.path.exists(thumbnail_path):
                    return thumbnail_path
            
            # Fall back to artist cover art
            return await self._get_artist_cover_art(album.artist_name)
            
        except Exception as e:
            logger.error(f"Failed to get album cover art: {e}")
            return "/static/images/default_album_cover.jpg"
    
    async def _get_artist_banner_art(self, artist_name: str) -> Optional[str]:
        """Get banner/header art for artist"""
        try:
            # Similar to cover art but for banners
            banner_art_dir = "/data/banner_art/artists"
            os.makedirs(banner_art_dir, exist_ok=True)
            
            safe_name = "".join(c for c in artist_name if c.isalnum() or c in (' ', '-', '_')).strip()
            local_path = f"{banner_art_dir}/{safe_name}_banner.jpg"
            
            if os.path.exists(local_path):
                return local_path
            
            return None  # No banner art available
            
        except Exception as e:
            logger.error(f"Failed to get banner art for artist {artist_name}: {e}")
            return None
    
    async def _fetch_external_cover_art(self, name: str, art_type: str) -> Optional[str]:
        """Fetch cover art from external sources (placeholder)"""
        try:
            # This would implement actual API calls to Last.fm, MusicBrainz, Spotify, etc.
            # For now, return None to indicate no external art found
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch external cover art for {name}: {e}")
            return None
    
    async def _detect_artist_genres(self, videos: List[Video]) -> List[str]:
        """Detect genres for artist based on their videos"""
        try:
            # This is a simplified implementation
            # In reality, you'd analyze video metadata, descriptions, etc.
            genres = set()
            
            # Check video descriptions for genre keywords
            genre_keywords = {
                'pop': ['pop', 'mainstream', 'radio'],
                'rock': ['rock', 'guitar', 'band'],
                'hip-hop': ['hip-hop', 'rap', 'urban'],
                'electronic': ['electronic', 'edm', 'dance'],
                'country': ['country', 'folk', 'acoustic'],
                'r&b': ['r&b', 'soul', 'rnb'],
                'jazz': ['jazz', 'swing', 'blues'],
                'classical': ['classical', 'orchestra', 'symphony']
            }
            
            for video in videos:
                if video.description:
                    desc_lower = video.description.lower()
                    for genre, keywords in genre_keywords.items():
                        if any(keyword in desc_lower for keyword in keywords):
                            genres.add(genre)
            
            return list(genres)[:3]  # Return max 3 genres
            
        except Exception as e:
            logger.error(f"Failed to detect artist genres: {e}")
            return []
    
    async def _detect_simple_genres(self, artist_name: str) -> List[str]:
        """Simple genre detection based on artist name"""
        try:
            # Very basic genre detection for demo purposes
            # In reality, this would use external APIs or machine learning
            name_lower = artist_name.lower()
            
            if any(word in name_lower for word in ['mc', 'lil', 'big']):
                return ['hip-hop']
            elif any(word in name_lower for word in ['dj', 'electronic']):
                return ['electronic']
            elif 'band' in name_lower:
                return ['rock']
            else:
                return ['pop']
                
        except Exception as e:
            logger.error(f"Failed to detect simple genres: {e}")
            return []
    
    async def _find_similar_artists(self, artist_id: int, genres: List[str]) -> List[Dict[str, Any]]:
        """Find similar artists based on genres and other factors"""
        try:
            similar = []
            
            async with get_async_session() as session:
                # Find artists with similar genres (simplified)
                # This would be much more sophisticated in a real implementation
                query = select(Artist.id, Artist.name).where(
                    Artist.id != artist_id
                ).limit(5)
                
                result = await session.execute(query)
                artists = result.all()
                
                for artist in artists:
                    similar.append({
                        'id': artist.id,
                        'name': artist.name,
                        'similarity_score': 0.8  # Placeholder score
                    })
            
            return similar
            
        except Exception as e:
            logger.error(f"Failed to find similar artists: {e}")
            return []
    
    async def _get_artist_albums(self, artist_id: int, videos: List[Video]) -> List[AlbumCard]:
        """Get album groupings for specific artist"""
        try:
            return await self._detect_artist_albums(None, artist_id, videos[0].artist_name if videos else "Unknown")
            
        except Exception as e:
            logger.error(f"Failed to get artist albums: {e}")
            return []
    
    def _video_to_dict(self, video: Video) -> Dict[str, Any]:
        """Convert video object to dictionary"""
        return {
            'id': video.id,
            'title': video.title,
            'duration': video.duration,
            'view_count': video.view_count or 0,
            'created_at': video.created_at.isoformat() if video.created_at else None,
            'is_music_video': video.is_music_video or False,
            'thumbnail_url': f"/api/thumbnails/video/{video.id}"
        }

# Global service instance
_artist_browser_service = None

async def get_artist_browser_service(config: Optional[Dict] = None) -> ArtistBrowserService:
    """Get global artist browser service instance"""
    global _artist_browser_service
    
    if _artist_browser_service is None:
        _artist_browser_service = ArtistBrowserService(config)
        await _artist_browser_service.initialize()
    
    return _artist_browser_service