"""
Playlist Management Service - Phase 3 Week 30
Consumer-focused playlist management with smart playlists and music video organization
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
import hashlib
import random

from src.utils.logger import get_logger
from src.services.redis_service import get_redis_client
from src.services.music_video_detector import get_music_video_detector
from src.services.enhanced_artist_discovery_service import get_enhanced_artist_discovery
from src.database.async_connection import get_async_session
from src.database.models import Video, Artist
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, text
from sqlalchemy.orm import selectinload

logger = get_logger("mvidarr.playlist_management")

class PlaylistType(Enum):
    """Types of playlists"""
    MANUAL = "manual"                    # User-created manual playlists
    SMART = "smart"                      # Auto-updating smart playlists
    RECENT_ADDITIONS = "recent_additions"  # Recently added videos
    MOST_PLAYED = "most_played"          # Most viewed videos
    FAVORITES = "favorites"              # User favorites
    ARTIST_COLLECTION = "artist_collection"  # All videos from specific artist
    GENRE_MIX = "genre_mix"              # Genre-based mix
    DECADE_MIX = "decade_mix"            # Era-based mix
    DISCOVERY = "discovery"              # New music discovery
    CUSTOM_MIX = "custom_mix"            # Custom algorithmic mix

class PlaylistPrivacy(Enum):
    """Playlist privacy levels"""
    PRIVATE = "private"                  # Only visible to creator
    SHARED = "shared"                    # Shared with specific users
    PUBLIC = "public"                    # Visible to all users

class SmartPlaylistRule(Enum):
    """Smart playlist rule types"""
    ARTIST_IS = "artist_is"
    ARTIST_CONTAINS = "artist_contains"
    TITLE_CONTAINS = "title_contains"
    GENRE_IS = "genre_is"
    DURATION_GREATER_THAN = "duration_greater_than"
    DURATION_LESS_THAN = "duration_less_than"
    ADDED_IN_LAST_DAYS = "added_in_last_days"
    VIEW_COUNT_GREATER_THAN = "view_count_greater_than"
    IS_MUSIC_VIDEO = "is_music_video"
    QUALITY_IS = "quality_is"
    YEAR_IS = "year_is"
    YEAR_BETWEEN = "year_between"

@dataclass
class PlaylistRule:
    """Smart playlist rule definition"""
    rule_type: SmartPlaylistRule
    operator: str  # 'equals', 'contains', 'greater_than', 'less_than', 'between'
    value: Any
    secondary_value: Optional[Any] = None  # For 'between' operations

@dataclass
class PlaylistItem:
    """Individual playlist item"""
    video_id: int
    position: int
    added_at: datetime
    added_by_user_id: Optional[int] = None
    custom_title: Optional[str] = None  # Custom title override
    notes: Optional[str] = None

@dataclass
class PlaylistStats:
    """Playlist statistics"""
    total_videos: int
    total_duration: int
    total_size_bytes: int
    most_played_video_id: Optional[int]
    average_video_duration: int
    music_video_count: int
    unique_artists_count: int
    last_updated: datetime
    play_count: int

@dataclass
class Playlist:
    """Complete playlist definition"""
    playlist_id: str
    name: str
    description: str
    playlist_type: PlaylistType
    privacy: PlaylistPrivacy
    created_by_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    cover_image_path: Optional[str]
    items: List[PlaylistItem]
    smart_rules: List[PlaylistRule]  # For smart playlists
    tags: List[str]
    stats: PlaylistStats
    is_favorite: bool = False
    play_count: int = 0

@dataclass
class PlaylistCollection:
    """Collection of playlists for browsing"""
    playlists: List[Playlist]
    total_count: int
    featured_playlists: List[Playlist]
    recent_playlists: List[Playlist]
    popular_playlists: List[Playlist]

class PlaylistManagementService:
    """Consumer-focused playlist management service"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.music_video_detector = None
        self.artist_discovery = None
        
        # Playlist configuration
        self.max_playlist_size = 1000  # Consumer-friendly limit
        self.max_playlists_per_user = 100
        self.auto_save_interval = 30  # seconds
        
        # Smart playlist update intervals
        self.smart_playlist_update_intervals = {
            PlaylistType.RECENT_ADDITIONS: 3600,      # 1 hour
            PlaylistType.MOST_PLAYED: 86400,          # 24 hours  
            PlaylistType.DISCOVERY: 86400 * 3,        # 3 days
            PlaylistType.GENRE_MIX: 86400 * 7,        # 1 week
            PlaylistType.DECADE_MIX: 86400 * 7        # 1 week
        }
        
        # Default smart playlists
        self.default_smart_playlists = [
            {
                'name': 'Recently Added',
                'type': PlaylistType.RECENT_ADDITIONS,
                'description': 'Videos added in the last 30 days',
                'rules': [
                    PlaylistRule(SmartPlaylistRule.ADDED_IN_LAST_DAYS, 'equals', 30)
                ]
            },
            {
                'name': 'Most Played',
                'type': PlaylistType.MOST_PLAYED,
                'description': 'Your most watched music videos',
                'rules': [
                    PlaylistRule(SmartPlaylistRule.IS_MUSIC_VIDEO, 'equals', True),
                    PlaylistRule(SmartPlaylistRule.VIEW_COUNT_GREATER_THAN, 'greater_than', 0)
                ]
            },
            {
                'name': 'Music Videos Only',
                'type': PlaylistType.SMART,
                'description': 'All confirmed music videos in your collection',
                'rules': [
                    PlaylistRule(SmartPlaylistRule.IS_MUSIC_VIDEO, 'equals', True)
                ]
            },
            {
                'name': 'High Quality Videos',
                'type': PlaylistType.SMART,
                'description': 'HD and higher quality videos',
                'rules': [
                    PlaylistRule(SmartPlaylistRule.QUALITY_IS, 'equals', '720p')
                ]
            }
        ]
    
    async def initialize(self):
        """Initialize playlist management service"""
        try:
            self.redis_client = await get_redis_client()
            self.music_video_detector = await get_music_video_detector()
            self.artist_discovery = await get_enhanced_artist_discovery()
            
            # Create default smart playlists if they don't exist
            await self._create_default_playlists()
            
            logger.info("Playlist management service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize playlist management service: {e}")
            raise
    
    async def create_playlist(
        self,
        name: str,
        description: str = "",
        playlist_type: PlaylistType = PlaylistType.MANUAL,
        privacy: PlaylistPrivacy = PlaylistPrivacy.PRIVATE,
        user_id: Optional[int] = None,
        smart_rules: Optional[List[PlaylistRule]] = None,
        tags: Optional[List[str]] = None
    ) -> Playlist:
        """Create a new playlist"""
        try:
            # Generate playlist ID
            playlist_id = f"playlist_{int(datetime.now().timestamp())}_{hashlib.md5(name.encode()).hexdigest()[:8]}"
            
            # Create playlist
            now = datetime.now()
            playlist = Playlist(
                playlist_id=playlist_id,
                name=name,
                description=description,
                playlist_type=playlist_type,
                privacy=privacy,
                created_by_user_id=user_id,
                created_at=now,
                updated_at=now,
                cover_image_path=None,
                items=[],
                smart_rules=smart_rules or [],
                tags=tags or [],
                stats=PlaylistStats(
                    total_videos=0,
                    total_duration=0,
                    total_size_bytes=0,
                    most_played_video_id=None,
                    average_video_duration=0,
                    music_video_count=0,
                    unique_artists_count=0,
                    last_updated=now,
                    play_count=0
                )
            )
            
            # If it's a smart playlist, populate it
            if playlist_type == PlaylistType.SMART and smart_rules:
                await self._update_smart_playlist(playlist)
            
            # Save playlist
            await self._save_playlist(playlist)
            
            logger.info(f"Created playlist '{name}' ({playlist_id}) with {len(playlist.items)} items")
            
            return playlist
            
        except Exception as e:
            logger.error(f"Failed to create playlist: {e}")
            raise
    
    async def add_videos_to_playlist(
        self,
        playlist_id: str,
        video_ids: List[int],
        user_id: Optional[int] = None,
        position: Optional[int] = None
    ) -> Playlist:
        """Add videos to a playlist"""
        try:
            playlist = await self._load_playlist(playlist_id)
            if not playlist:
                raise ValueError(f"Playlist {playlist_id} not found")
            
            if playlist.playlist_type != PlaylistType.MANUAL:
                raise ValueError("Cannot manually add videos to non-manual playlists")
            
            # Check playlist size limit
            if len(playlist.items) + len(video_ids) > self.max_playlist_size:
                raise ValueError(f"Playlist size limit ({self.max_playlist_size}) would be exceeded")
            
            # Verify videos exist
            async with get_async_session() as session:
                videos_query = select(Video).where(Video.id.in_(video_ids))
                result = await session.execute(videos_query)
                videos = result.scalars().all()
                
                if len(videos) != len(video_ids):
                    found_ids = {v.id for v in videos}
                    missing_ids = set(video_ids) - found_ids
                    raise ValueError(f"Videos not found: {missing_ids}")
                
                # Add videos to playlist
                current_max_position = max([item.position for item in playlist.items], default=0)
                
                for i, video_id in enumerate(video_ids):
                    new_position = position + i if position is not None else current_max_position + i + 1
                    
                    # Check if video is already in playlist
                    if any(item.video_id == video_id for item in playlist.items):
                        logger.warning(f"Video {video_id} already in playlist {playlist_id}")
                        continue
                    
                    playlist_item = PlaylistItem(
                        video_id=video_id,
                        position=new_position,
                        added_at=datetime.now(),
                        added_by_user_id=user_id
                    )
                    playlist.items.append(playlist_item)
                
                # Update playlist stats
                await self._update_playlist_stats(playlist, session)
                
                # Save playlist
                await self._save_playlist(playlist)
                
                logger.info(f"Added {len(video_ids)} videos to playlist {playlist_id}")
                
                return playlist
                
        except Exception as e:
            logger.error(f"Failed to add videos to playlist: {e}")
            raise
    
    async def remove_videos_from_playlist(
        self,
        playlist_id: str,
        video_ids: List[int],
        user_id: Optional[int] = None
    ) -> Playlist:
        """Remove videos from a playlist"""
        try:
            playlist = await self._load_playlist(playlist_id)
            if not playlist:
                raise ValueError(f"Playlist {playlist_id} not found")
            
            if playlist.playlist_type != PlaylistType.MANUAL:
                raise ValueError("Cannot manually remove videos from non-manual playlists")
            
            # Remove videos
            original_count = len(playlist.items)
            playlist.items = [item for item in playlist.items if item.video_id not in video_ids]
            removed_count = original_count - len(playlist.items)
            
            # Reorder positions
            for i, item in enumerate(sorted(playlist.items, key=lambda x: x.position)):
                item.position = i + 1
            
            # Update playlist stats
            async with get_async_session() as session:
                await self._update_playlist_stats(playlist, session)
            
            # Save playlist
            await self._save_playlist(playlist)
            
            logger.info(f"Removed {removed_count} videos from playlist {playlist_id}")
            
            return playlist
            
        except Exception as e:
            logger.error(f"Failed to remove videos from playlist: {e}")
            raise
    
    async def reorder_playlist(
        self,
        playlist_id: str,
        video_id: int,
        new_position: int,
        user_id: Optional[int] = None
    ) -> Playlist:
        """Reorder a video within a playlist"""
        try:
            playlist = await self._load_playlist(playlist_id)
            if not playlist:
                raise ValueError(f"Playlist {playlist_id} not found")
            
            # Find the video item
            video_item = None
            for item in playlist.items:
                if item.video_id == video_id:
                    video_item = item
                    break
            
            if not video_item:
                raise ValueError(f"Video {video_id} not found in playlist")
            
            # Remove from current position
            playlist.items.remove(video_item)
            
            # Insert at new position
            new_position = max(1, min(new_position, len(playlist.items) + 1))
            playlist.items.insert(new_position - 1, video_item)
            
            # Update all positions
            for i, item in enumerate(playlist.items):
                item.position = i + 1
            
            playlist.updated_at = datetime.now()
            
            # Save playlist
            await self._save_playlist(playlist)
            
            logger.info(f"Reordered video {video_id} to position {new_position} in playlist {playlist_id}")
            
            return playlist
            
        except Exception as e:
            logger.error(f"Failed to reorder playlist: {e}")
            raise
    
    async def update_playlist(
        self,
        playlist_id: str,
        updates: Dict[str, Any],
        user_id: Optional[int] = None
    ) -> Playlist:
        """Update playlist metadata"""
        try:
            playlist = await self._load_playlist(playlist_id)
            if not playlist:
                raise ValueError(f"Playlist {playlist_id} not found")
            
            # Update allowed fields
            if 'name' in updates:
                playlist.name = updates['name']
            
            if 'description' in updates:
                playlist.description = updates['description']
            
            if 'privacy' in updates:
                playlist.privacy = PlaylistPrivacy(updates['privacy'])
            
            if 'tags' in updates:
                playlist.tags = updates['tags']
            
            if 'cover_image_path' in updates:
                playlist.cover_image_path = updates['cover_image_path']
            
            playlist.updated_at = datetime.now()
            
            # Save playlist
            await self._save_playlist(playlist)
            
            logger.info(f"Updated playlist {playlist_id}")
            
            return playlist
            
        except Exception as e:
            logger.error(f"Failed to update playlist: {e}")
            raise
    
    async def delete_playlist(self, playlist_id: str, user_id: Optional[int] = None) -> bool:
        """Delete a playlist"""
        try:
            playlist = await self._load_playlist(playlist_id)
            if not playlist:
                return False
            
            # Remove from Redis
            cache_key = f"playlist:{playlist_id}"
            await self.redis_client.delete(cache_key)
            
            # Remove from user's playlist list
            if user_id:
                user_playlists_key = f"user_playlists:{user_id}"
                await self.redis_client.srem(user_playlists_key, playlist_id)
            
            logger.info(f"Deleted playlist {playlist_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete playlist: {e}")
            return False
    
    async def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        """Get a specific playlist"""
        try:
            return await self._load_playlist(playlist_id)
            
        except Exception as e:
            logger.error(f"Failed to get playlist {playlist_id}: {e}")
            return None
    
    async def list_playlists(
        self,
        user_id: Optional[int] = None,
        playlist_type: Optional[PlaylistType] = None,
        limit: int = 50,
        offset: int = 0
    ) -> PlaylistCollection:
        """List playlists with filtering"""
        try:
            all_playlists = await self._load_all_playlists(user_id)
            
            # Filter by type if specified
            if playlist_type:
                filtered_playlists = [p for p in all_playlists if p.playlist_type == playlist_type]
            else:
                filtered_playlists = all_playlists
            
            # Sort by most recently updated
            filtered_playlists.sort(key=lambda p: p.updated_at, reverse=True)
            
            # Apply pagination
            total_count = len(filtered_playlists)
            paginated_playlists = filtered_playlists[offset:offset + limit]
            
            # Get featured, recent, and popular playlists
            featured = [p for p in all_playlists if p.is_favorite][:5]
            recent = [p for p in all_playlists if p.playlist_type == PlaylistType.MANUAL][:5]
            popular = sorted([p for p in all_playlists], key=lambda p: p.play_count, reverse=True)[:5]
            
            return PlaylistCollection(
                playlists=paginated_playlists,
                total_count=total_count,
                featured_playlists=featured,
                recent_playlists=recent,
                popular_playlists=popular
            )
            
        except Exception as e:
            logger.error(f"Failed to list playlists: {e}")
            return PlaylistCollection([], 0, [], [], [])
    
    async def create_smart_playlist(
        self,
        name: str,
        rules: List[PlaylistRule],
        description: str = "",
        user_id: Optional[int] = None
    ) -> Playlist:
        """Create a smart playlist with rules"""
        try:
            playlist = await self.create_playlist(
                name=name,
                description=description,
                playlist_type=PlaylistType.SMART,
                user_id=user_id,
                smart_rules=rules
            )
            
            return playlist
            
        except Exception as e:
            logger.error(f"Failed to create smart playlist: {e}")
            raise
    
    async def update_smart_playlists(self, force: bool = False) -> Dict[str, Any]:
        """Update all smart playlists that need updating"""
        try:
            updated_count = 0
            error_count = 0
            
            # Get all smart playlists
            all_playlists = await self._load_all_playlists()
            smart_playlists = [p for p in all_playlists if p.playlist_type in self.smart_playlist_update_intervals]
            
            for playlist in smart_playlists:
                try:
                    # Check if update is needed
                    if not force:
                        update_interval = self.smart_playlist_update_intervals.get(playlist.playlist_type, 86400)
                        time_since_update = (datetime.now() - playlist.stats.last_updated).total_seconds()
                        
                        if time_since_update < update_interval:
                            continue
                    
                    # Update the playlist
                    await self._update_smart_playlist(playlist)
                    await self._save_playlist(playlist)
                    updated_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to update smart playlist {playlist.playlist_id}: {e}")
                    error_count += 1
            
            logger.info(f"Updated {updated_count} smart playlists, {error_count} errors")
            
            return {
                'updated_count': updated_count,
                'error_count': error_count,
                'total_smart_playlists': len(smart_playlists)
            }
            
        except Exception as e:
            logger.error(f"Failed to update smart playlists: {e}")
            return {'updated_count': 0, 'error_count': 1, 'total_smart_playlists': 0}
    
    async def generate_discovery_playlist(self, user_id: Optional[int] = None) -> Playlist:
        """Generate a discovery playlist with new/unplayed content"""
        try:
            async with get_async_session() as session:
                # Get videos the user hasn't watched much
                discovery_query = select(Video).where(
                    and_(
                        Video.is_music_video == True,
                        Video.view_count <= 2  # Low play count
                    )
                ).order_by(desc(Video.created_at)).limit(50)
                
                result = await session.execute(discovery_query)
                discovery_videos = result.scalars().all()
                
                # Shuffle for variety
                random.shuffle(list(discovery_videos))
                
                # Take top 25
                selected_videos = discovery_videos[:25]
                
                # Create discovery playlist
                playlist = await self.create_playlist(
                    name=f"Discovery Mix - {datetime.now().strftime('%B %d')}",
                    description="New and lesser-played music videos for discovery",
                    playlist_type=PlaylistType.DISCOVERY,
                    user_id=user_id
                )
                
                # Add videos
                video_ids = [v.id for v in selected_videos]
                if video_ids:
                    await self.add_videos_to_playlist(playlist.playlist_id, video_ids, user_id)
                
                logger.info(f"Generated discovery playlist with {len(video_ids)} videos")
                
                return playlist
                
        except Exception as e:
            logger.error(f"Failed to generate discovery playlist: {e}")
            raise
    
    async def _update_smart_playlist(self, playlist: Playlist):
        """Update a smart playlist based on its rules"""
        try:
            async with get_async_session() as session:
                # Build query based on smart rules
                base_query = select(Video).options(selectinload(Video.artist))
                conditions = []
                
                for rule in playlist.smart_rules:
                    condition = await self._build_rule_condition(rule)
                    if condition is not None:
                        conditions.append(condition)
                
                if conditions:
                    base_query = base_query.where(and_(*conditions))
                
                # Apply default sorting and limits
                base_query = base_query.order_by(desc(Video.created_at)).limit(self.max_playlist_size)
                
                # Execute query
                result = await session.execute(base_query)
                videos = result.scalars().all()
                
                # Update playlist items
                playlist.items = []
                for i, video in enumerate(videos):
                    playlist_item = PlaylistItem(
                        video_id=video.id,
                        position=i + 1,
                        added_at=datetime.now()
                    )
                    playlist.items.append(playlist_item)
                
                # Update stats
                await self._update_playlist_stats(playlist, session)
                
                playlist.updated_at = datetime.now()
                
                logger.info(f"Updated smart playlist {playlist.playlist_id} with {len(videos)} videos")
                
        except Exception as e:
            logger.error(f"Failed to update smart playlist: {e}")
    
    async def _build_rule_condition(self, rule: PlaylistRule):
        """Build SQL condition from playlist rule"""
        try:
            if rule.rule_type == SmartPlaylistRule.ARTIST_IS:
                return Video.artist_name.ilike(f"%{rule.value}%")
            elif rule.rule_type == SmartPlaylistRule.ARTIST_CONTAINS:
                return Video.artist_name.ilike(f"%{rule.value}%")
            elif rule.rule_type == SmartPlaylistRule.TITLE_CONTAINS:
                return Video.title.ilike(f"%{rule.value}%")
            elif rule.rule_type == SmartPlaylistRule.DURATION_GREATER_THAN:
                return Video.duration >= rule.value
            elif rule.rule_type == SmartPlaylistRule.DURATION_LESS_THAN:
                return Video.duration <= rule.value
            elif rule.rule_type == SmartPlaylistRule.ADDED_IN_LAST_DAYS:
                cutoff_date = datetime.now() - timedelta(days=rule.value)
                return Video.created_at >= cutoff_date
            elif rule.rule_type == SmartPlaylistRule.VIEW_COUNT_GREATER_THAN:
                return Video.view_count >= rule.value
            elif rule.rule_type == SmartPlaylistRule.IS_MUSIC_VIDEO:
                return Video.is_music_video == bool(rule.value)
            elif rule.rule_type == SmartPlaylistRule.YEAR_IS:
                return func.extract('year', Video.created_at) == rule.value
            elif rule.rule_type == SmartPlaylistRule.YEAR_BETWEEN:
                return and_(
                    func.extract('year', Video.created_at) >= rule.value,
                    func.extract('year', Video.created_at) <= rule.secondary_value
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to build rule condition: {e}")
            return None
    
    async def _update_playlist_stats(self, playlist: Playlist, session: AsyncSession):
        """Update playlist statistics"""
        try:
            if not playlist.items:
                playlist.stats = PlaylistStats(
                    total_videos=0,
                    total_duration=0,
                    total_size_bytes=0,
                    most_played_video_id=None,
                    average_video_duration=0,
                    music_video_count=0,
                    unique_artists_count=0,
                    last_updated=datetime.now(),
                    play_count=playlist.stats.play_count if playlist.stats else 0
                )
                return
            
            # Get video details
            video_ids = [item.video_id for item in playlist.items]
            videos_query = select(Video).where(Video.id.in_(video_ids)).options(selectinload(Video.artist))
            result = await session.execute(videos_query)
            videos = result.scalars().all()
            
            # Calculate stats
            total_videos = len(videos)
            total_duration = sum(v.duration or 0 for v in videos)
            total_size_bytes = sum(v.file_size or 0 for v in videos)
            music_video_count = sum(1 for v in videos if v.is_music_video)
            unique_artists = set(v.artist_name for v in videos if v.artist_name)
            
            # Find most played video
            most_played_video = max(videos, key=lambda v: v.view_count or 0) if videos else None
            
            playlist.stats = PlaylistStats(
                total_videos=total_videos,
                total_duration=total_duration,
                total_size_bytes=total_size_bytes,
                most_played_video_id=most_played_video.id if most_played_video else None,
                average_video_duration=total_duration // max(total_videos, 1),
                music_video_count=music_video_count,
                unique_artists_count=len(unique_artists),
                last_updated=datetime.now(),
                play_count=playlist.stats.play_count if playlist.stats else 0
            )
            
        except Exception as e:
            logger.error(f"Failed to update playlist stats: {e}")
    
    async def _save_playlist(self, playlist: Playlist):
        """Save playlist to Redis"""
        try:
            cache_key = f"playlist:{playlist.playlist_id}"
            playlist_data = {
                'playlist_id': playlist.playlist_id,
                'name': playlist.name,
                'description': playlist.description,
                'playlist_type': playlist.playlist_type.value,
                'privacy': playlist.privacy.value,
                'created_by_user_id': playlist.created_by_user_id,
                'created_at': playlist.created_at.isoformat(),
                'updated_at': playlist.updated_at.isoformat(),
                'cover_image_path': playlist.cover_image_path,
                'items': [
                    {
                        'video_id': item.video_id,
                        'position': item.position,
                        'added_at': item.added_at.isoformat(),
                        'added_by_user_id': item.added_by_user_id,
                        'custom_title': item.custom_title,
                        'notes': item.notes
                    } for item in playlist.items
                ],
                'smart_rules': [
                    {
                        'rule_type': rule.rule_type.value,
                        'operator': rule.operator,
                        'value': rule.value,
                        'secondary_value': rule.secondary_value
                    } for rule in playlist.smart_rules
                ],
                'tags': playlist.tags,
                'stats': {
                    'total_videos': playlist.stats.total_videos,
                    'total_duration': playlist.stats.total_duration,
                    'total_size_bytes': playlist.stats.total_size_bytes,
                    'most_played_video_id': playlist.stats.most_played_video_id,
                    'average_video_duration': playlist.stats.average_video_duration,
                    'music_video_count': playlist.stats.music_video_count,
                    'unique_artists_count': playlist.stats.unique_artists_count,
                    'last_updated': playlist.stats.last_updated.isoformat(),
                    'play_count': playlist.stats.play_count
                },
                'is_favorite': playlist.is_favorite,
                'play_count': playlist.play_count
            }
            
            await self.redis_client.setex(cache_key, 86400 * 7, json.dumps(playlist_data))
            
            # Add to user's playlist set if user_id exists
            if playlist.created_by_user_id:
                user_playlists_key = f"user_playlists:{playlist.created_by_user_id}"
                await self.redis_client.sadd(user_playlists_key, playlist.playlist_id)
            
        except Exception as e:
            logger.error(f"Failed to save playlist {playlist.playlist_id}: {e}")
    
    async def _load_playlist(self, playlist_id: str) -> Optional[Playlist]:
        """Load playlist from Redis"""
        try:
            cache_key = f"playlist:{playlist_id}"
            playlist_data = await self.redis_client.get(cache_key)
            
            if not playlist_data:
                return None
            
            data = json.loads(playlist_data)
            
            # Reconstruct playlist object
            items = []
            for item_data in data['items']:
                item = PlaylistItem(
                    video_id=item_data['video_id'],
                    position=item_data['position'],
                    added_at=datetime.fromisoformat(item_data['added_at']),
                    added_by_user_id=item_data.get('added_by_user_id'),
                    custom_title=item_data.get('custom_title'),
                    notes=item_data.get('notes')
                )
                items.append(item)
            
            smart_rules = []
            for rule_data in data['smart_rules']:
                rule = PlaylistRule(
                    rule_type=SmartPlaylistRule(rule_data['rule_type']),
                    operator=rule_data['operator'],
                    value=rule_data['value'],
                    secondary_value=rule_data.get('secondary_value')
                )
                smart_rules.append(rule)
            
            stats_data = data['stats']
            stats = PlaylistStats(
                total_videos=stats_data['total_videos'],
                total_duration=stats_data['total_duration'],
                total_size_bytes=stats_data['total_size_bytes'],
                most_played_video_id=stats_data.get('most_played_video_id'),
                average_video_duration=stats_data['average_video_duration'],
                music_video_count=stats_data['music_video_count'],
                unique_artists_count=stats_data['unique_artists_count'],
                last_updated=datetime.fromisoformat(stats_data['last_updated']),
                play_count=stats_data['play_count']
            )
            
            playlist = Playlist(
                playlist_id=data['playlist_id'],
                name=data['name'],
                description=data['description'],
                playlist_type=PlaylistType(data['playlist_type']),
                privacy=PlaylistPrivacy(data['privacy']),
                created_by_user_id=data.get('created_by_user_id'),
                created_at=datetime.fromisoformat(data['created_at']),
                updated_at=datetime.fromisoformat(data['updated_at']),
                cover_image_path=data.get('cover_image_path'),
                items=items,
                smart_rules=smart_rules,
                tags=data.get('tags', []),
                stats=stats,
                is_favorite=data.get('is_favorite', False),
                play_count=data.get('play_count', 0)
            )
            
            return playlist
            
        except Exception as e:
            logger.error(f"Failed to load playlist {playlist_id}: {e}")
            return None
    
    async def _load_all_playlists(self, user_id: Optional[int] = None) -> List[Playlist]:
        """Load all playlists, optionally filtered by user"""
        try:
            playlists = []
            
            if user_id:
                # Get user's playlist IDs
                user_playlists_key = f"user_playlists:{user_id}"
                playlist_ids = await self.redis_client.smembers(user_playlists_key)
            else:
                # Get all playlist keys
                pattern = "playlist:*"
                keys = await self.redis_client.keys(pattern)
                playlist_ids = [key.split(':', 1)[1] for key in keys]
            
            # Load each playlist
            for playlist_id in playlist_ids:
                playlist = await self._load_playlist(playlist_id)
                if playlist:
                    playlists.append(playlist)
            
            return playlists
            
        except Exception as e:
            logger.error(f"Failed to load all playlists: {e}")
            return []
    
    async def _create_default_playlists(self):
        """Create default smart playlists if they don't exist"""
        try:
            for default_playlist in self.default_smart_playlists:
                # Check if playlist already exists
                existing = await self._find_playlist_by_name(default_playlist['name'])
                if existing:
                    continue
                
                # Create the default playlist
                await self.create_playlist(
                    name=default_playlist['name'],
                    description=default_playlist['description'],
                    playlist_type=default_playlist['type'],
                    smart_rules=default_playlist['rules']
                )
            
            logger.info(f"Ensured {len(self.default_smart_playlists)} default playlists exist")
            
        except Exception as e:
            logger.error(f"Failed to create default playlists: {e}")
    
    async def _find_playlist_by_name(self, name: str) -> Optional[Playlist]:
        """Find a playlist by name"""
        try:
            all_playlists = await self._load_all_playlists()
            for playlist in all_playlists:
                if playlist.name == name:
                    return playlist
            return None
            
        except Exception as e:
            logger.error(f"Failed to find playlist by name: {e}")
            return None

# Global service instance
_playlist_management_service = None

async def get_playlist_management_service(config: Optional[Dict] = None) -> PlaylistManagementService:
    """Get global playlist management service instance"""
    global _playlist_management_service
    
    if _playlist_management_service is None:
        _playlist_management_service = PlaylistManagementService(config)
        await _playlist_management_service.initialize()
    
    return _playlist_management_service