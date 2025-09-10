"""
Watch History Service - Phase 3 Week 30
Consumer-focused watch history tracking and continue watching features
"""

import asyncio
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
import hashlib

from src.utils.logger import get_logger
from src.services.redis_service import get_redis_client
from src.services.performance_monitor import get_performance_monitor
from src.database.async_connection import get_async_session
from src.database.models import Video, Artist
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, text
from sqlalchemy.orm import selectinload

logger = get_logger("mvidarr.watch_history")

class WatchStatus(Enum):
    """Video watch status"""
    NOT_STARTED = "not_started"      # Never watched
    STARTED = "started"               # Partially watched
    COMPLETED = "completed"           # Fully watched
    SKIPPED = "skipped"              # Skipped through quickly

class SessionType(Enum):
    """Types of viewing sessions"""
    SINGLE_VIDEO = "single_video"     # Watching individual video
    PLAYLIST = "playlist"             # Watching from playlist
    SHUFFLE = "shuffle"               # Random/shuffle mode
    ARTIST_BINGE = "artist_binge"     # Watching multiple from same artist
    DISCOVERY = "discovery"           # Discovery/recommended videos
    SEARCH_RESULT = "search_result"   # From search results

@dataclass
class WatchSession:
    """Individual watch session"""
    session_id: str
    user_id: Optional[int]
    video_id: int
    started_at: datetime
    ended_at: Optional[datetime]
    watch_duration: int  # seconds actually watched
    video_duration: int  # total video duration
    progress_percent: float  # 0-100
    session_type: SessionType
    source_context: Optional[str]  # playlist_id, search_query, etc.
    device_info: Optional[Dict[str, str]]
    quality_watched: Optional[str]
    is_completed: bool
    completion_threshold: float = 0.8  # 80% = completed

@dataclass
class VideoWatchHistory:
    """Complete watch history for a video"""
    video_id: int
    total_watch_time: int
    total_sessions: int
    first_watched: datetime
    last_watched: datetime
    completion_count: int
    current_progress_percent: float
    watch_status: WatchStatus
    sessions: List[WatchSession]
    favorite_marked_at: Optional[datetime] = None

@dataclass
class ContinueWatchingItem:
    """Item for continue watching list"""
    video_id: int
    title: str
    artist: str
    progress_percent: float
    last_watched: datetime
    thumbnail_url: str
    duration: int
    remaining_time: int
    session_type: SessionType
    source_context: Optional[str]

@dataclass
class WatchStatistics:
    """User watch statistics"""
    total_videos_watched: int
    total_watch_time_minutes: int
    average_session_length: int
    completion_rate: float
    favorite_genres: List[str]
    favorite_artists: List[str]
    most_active_hours: List[int]
    longest_session_minutes: int
    current_streak_days: int
    last_active_date: datetime

class WatchHistoryService:
    """Consumer-focused watch history and continue watching service"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.performance_monitor = None
        
        # Configuration
        self.completion_threshold = 0.8  # 80% watched = completed
        self.continue_watching_limit = 20  # Max items in continue watching
        self.session_timeout = 3600  # 1 hour session timeout
        self.history_retention_days = 365  # Keep history for 1 year
        
        # Progress tracking thresholds
        self.progress_save_intervals = [10, 25, 50, 75, 90]  # Save at these percentages
        self.minimum_watch_duration = 30  # Minimum 30 seconds to count as "watched"
        
    async def initialize(self):
        """Initialize watch history service"""
        try:
            self.redis_client = await get_redis_client()
            self.performance_monitor = await get_performance_monitor()
            
            logger.info("Watch history service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize watch history service: {e}")
            raise
    
    async def start_watch_session(
        self,
        video_id: int,
        user_id: Optional[int] = None,
        session_type: SessionType = SessionType.SINGLE_VIDEO,
        source_context: Optional[str] = None,
        device_info: Optional[Dict[str, str]] = None,
        quality: Optional[str] = None
    ) -> str:
        """Start a new watch session"""
        try:
            # Generate session ID
            session_id = f"session_{int(datetime.now().timestamp())}_{hashlib.md5(f'{video_id}_{user_id}'.encode()).hexdigest()[:8]}"
            
            # Get video duration
            async with get_async_session() as session:
                video_query = select(Video).where(Video.id == video_id)
                result = await session.execute(video_query)
                video = result.scalar_one_or_none()
                
                if not video:
                    raise ValueError(f"Video {video_id} not found")
                
                video_duration = video.duration or 0
            
            # Create watch session
            watch_session = WatchSession(
                session_id=session_id,
                user_id=user_id,
                video_id=video_id,
                started_at=datetime.now(),
                ended_at=None,
                watch_duration=0,
                video_duration=video_duration,
                progress_percent=0.0,
                session_type=session_type,
                source_context=source_context,
                device_info=device_info,
                quality_watched=quality,
                is_completed=False
            )
            
            # Save session
            await self._save_watch_session(watch_session)
            
            # Update video view count
            await self._increment_video_view_count(video_id)
            
            logger.info(f"Started watch session {session_id} for video {video_id}")
            
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to start watch session: {e}")
            raise
    
    async def update_watch_progress(
        self,
        session_id: str,
        current_time: int,
        total_time: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update watch progress for an active session"""
        try:
            # Load current session
            session = await self._load_watch_session(session_id)
            if not session:
                raise ValueError(f"Watch session {session_id} not found")
            
            # Calculate progress
            video_duration = total_time or session.video_duration
            if video_duration > 0:
                progress_percent = min(100.0, (current_time / video_duration) * 100)
            else:
                progress_percent = 0.0
            
            # Update session
            session.watch_duration = current_time
            session.progress_percent = progress_percent
            session.video_duration = video_duration
            
            # Check if completed
            if progress_percent >= (self.completion_threshold * 100):
                session.is_completed = True
            
            # Save updated session
            await self._save_watch_session(session)
            
            # Update video watch history
            await self._update_video_history(session)
            
            # Save to continue watching if appropriate
            if 5 <= progress_percent < 95 and current_time >= self.minimum_watch_duration:
                await self._add_to_continue_watching(session)
            
            logger.debug(f"Updated watch progress for session {session_id}: {progress_percent:.1f}%")
            
            return {
                'session_id': session_id,
                'progress_percent': progress_percent,
                'is_completed': session.is_completed,
                'current_time': current_time,
                'total_time': video_duration
            }
            
        except Exception as e:
            logger.error(f"Failed to update watch progress: {e}")
            return {}
    
    async def end_watch_session(self, session_id: str) -> WatchSession:
        """End a watch session"""
        try:
            # Load current session
            session = await self._load_watch_session(session_id)
            if not session:
                raise ValueError(f"Watch session {session_id} not found")
            
            # Mark session as ended
            session.ended_at = datetime.now()
            
            # Calculate total session time
            if session.started_at:
                total_session_time = (session.ended_at - session.started_at).total_seconds()
                session.watch_duration = min(session.watch_duration, int(total_session_time))
            
            # Final progress calculation
            if session.video_duration > 0:
                session.progress_percent = min(100.0, (session.watch_duration / session.video_duration) * 100)
            
            # Check completion status
            if session.progress_percent >= (self.completion_threshold * 100):
                session.is_completed = True
            
            # Save final session
            await self._save_watch_session(session)
            
            # Update video watch history
            await self._update_video_history(session)
            
            # Remove from continue watching if completed
            if session.is_completed:
                await self._remove_from_continue_watching(session.video_id, session.user_id)
            else:
                # Add to continue watching if partially watched
                if session.progress_percent >= 5:
                    await self._add_to_continue_watching(session)
            
            logger.info(f"Ended watch session {session_id}, {session.progress_percent:.1f}% watched")
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to end watch session: {e}")
            raise
    
    async def get_continue_watching(self, user_id: int, limit: int = 20) -> List[ContinueWatchingItem]:
        """Get continue watching list for user"""
        try:
            cache_key = f"continue_watching:{user_id}"
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                continue_watching_data = json.loads(cached_data)
                continue_watching_items = []
                
                # Get video details for each item
                async with get_async_session() as session:
                    for item_data in continue_watching_data[:limit]:
                        video_query = select(Video).where(Video.id == item_data['video_id']).options(selectinload(Video.artist))
                        result = await session.execute(video_query)
                        video = result.scalar_one_or_none()
                        
                        if video:
                            remaining_time = max(0, (video.duration or 0) - int((item_data['progress_percent'] / 100) * (video.duration or 0)))
                            
                            continue_item = ContinueWatchingItem(
                                video_id=video.id,
                                title=video.title or "Unknown Title",
                                artist=video.artist_name or "Unknown Artist",
                                progress_percent=item_data['progress_percent'],
                                last_watched=datetime.fromisoformat(item_data['last_watched']),
                                thumbnail_url=f"/api/thumbnails/video/{video.id}",
                                duration=video.duration or 0,
                                remaining_time=remaining_time,
                                session_type=SessionType(item_data['session_type']),
                                source_context=item_data.get('source_context')
                            )
                            continue_watching_items.append(continue_item)
                
                # Sort by most recently watched
                continue_watching_items.sort(key=lambda x: x.last_watched, reverse=True)
                
                return continue_watching_items
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to get continue watching for user {user_id}: {e}")
            return []
    
    async def get_video_watch_history(self, video_id: int, user_id: Optional[int] = None) -> Optional[VideoWatchHistory]:
        """Get complete watch history for a video"""
        try:
            cache_key = f"video_history:{video_id}" + (f":{user_id}" if user_id else "")
            cached_data = await self.redis_client.get(cache_key)
            
            if cached_data:
                history_data = json.loads(cached_data)
                
                # Reconstruct sessions
                sessions = []
                for session_data in history_data.get('sessions', []):
                    session = WatchSession(
                        session_id=session_data['session_id'],
                        user_id=session_data.get('user_id'),
                        video_id=session_data['video_id'],
                        started_at=datetime.fromisoformat(session_data['started_at']),
                        ended_at=datetime.fromisoformat(session_data['ended_at']) if session_data.get('ended_at') else None,
                        watch_duration=session_data['watch_duration'],
                        video_duration=session_data['video_duration'],
                        progress_percent=session_data['progress_percent'],
                        session_type=SessionType(session_data['session_type']),
                        source_context=session_data.get('source_context'),
                        device_info=session_data.get('device_info'),
                        quality_watched=session_data.get('quality_watched'),
                        is_completed=session_data['is_completed']
                    )
                    sessions.append(session)
                
                history = VideoWatchHistory(
                    video_id=history_data['video_id'],
                    total_watch_time=history_data['total_watch_time'],
                    total_sessions=history_data['total_sessions'],
                    first_watched=datetime.fromisoformat(history_data['first_watched']),
                    last_watched=datetime.fromisoformat(history_data['last_watched']),
                    completion_count=history_data['completion_count'],
                    current_progress_percent=history_data['current_progress_percent'],
                    watch_status=WatchStatus(history_data['watch_status']),
                    sessions=sessions,
                    favorite_marked_at=datetime.fromisoformat(history_data['favorite_marked_at']) if history_data.get('favorite_marked_at') else None
                )
                
                return history
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get video watch history: {e}")
            return None
    
    async def get_watch_statistics(self, user_id: int, days: int = 30) -> WatchStatistics:
        """Get user watch statistics"""
        try:
            # Get user's session history
            pattern = f"session:{user_id}:*"
            session_keys = await self.redis_client.keys(pattern)
            
            sessions = []
            for key in session_keys:
                session_data = await self.redis_client.get(key)
                if session_data:
                    session_info = json.loads(session_data)
                    # Check if within date range
                    session_date = datetime.fromisoformat(session_info['started_at'])
                    if (datetime.now() - session_date).days <= days:
                        sessions.append(session_info)
            
            if not sessions:
                # Return empty statistics
                return WatchStatistics(
                    total_videos_watched=0,
                    total_watch_time_minutes=0,
                    average_session_length=0,
                    completion_rate=0.0,
                    favorite_genres=[],
                    favorite_artists=[],
                    most_active_hours=[],
                    longest_session_minutes=0,
                    current_streak_days=0,
                    last_active_date=datetime.now()
                )
            
            # Calculate statistics
            total_videos = len(set(s['video_id'] for s in sessions))
            total_watch_time = sum(s['watch_duration'] for s in sessions)
            completed_sessions = sum(1 for s in sessions if s.get('is_completed', False))
            completion_rate = (completed_sessions / len(sessions)) * 100 if sessions else 0
            
            # Average session length
            session_lengths = []
            for session in sessions:
                if session.get('ended_at') and session.get('started_at'):
                    start = datetime.fromisoformat(session['started_at'])
                    end = datetime.fromisoformat(session['ended_at'])
                    length = (end - start).total_seconds()
                    session_lengths.append(length)
            
            avg_session_length = int(sum(session_lengths) / len(session_lengths)) if session_lengths else 0
            longest_session = int(max(session_lengths)) if session_lengths else 0
            
            # Most active hours
            hours_activity = {}
            for session in sessions:
                hour = datetime.fromisoformat(session['started_at']).hour
                hours_activity[hour] = hours_activity.get(hour, 0) + 1
            
            most_active_hours = sorted(hours_activity.keys(), key=lambda x: hours_activity[x], reverse=True)[:3]
            
            # Calculate current streak
            current_streak = await self._calculate_watch_streak(user_id)
            
            # Get last active date
            last_active = max(datetime.fromisoformat(s['started_at']) for s in sessions) if sessions else datetime.now()
            
            return WatchStatistics(
                total_videos_watched=total_videos,
                total_watch_time_minutes=total_watch_time // 60,
                average_session_length=avg_session_length,
                completion_rate=completion_rate,
                favorite_genres=[],  # Would require genre analysis
                favorite_artists=[],  # Would require artist analysis
                most_active_hours=most_active_hours,
                longest_session_minutes=longest_session // 60,
                current_streak_days=current_streak,
                last_active_date=last_active
            )
            
        except Exception as e:
            logger.error(f"Failed to get watch statistics: {e}")
            return WatchStatistics(0, 0, 0, 0.0, [], [], [], 0, 0, datetime.now())
    
    async def mark_as_watched(self, video_id: int, user_id: Optional[int] = None) -> bool:
        """Mark a video as fully watched"""
        try:
            # Create a completed session
            session_id = await self.start_watch_session(
                video_id=video_id,
                user_id=user_id,
                session_type=SessionType.SINGLE_VIDEO
            )
            
            # Load session and mark as completed
            session = await self._load_watch_session(session_id)
            if session:
                session.watch_duration = session.video_duration
                session.progress_percent = 100.0
                session.is_completed = True
                session.ended_at = datetime.now()
                
                await self._save_watch_session(session)
                await self._update_video_history(session)
                await self._remove_from_continue_watching(video_id, user_id)
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to mark video as watched: {e}")
            return False
    
    async def clear_continue_watching(self, user_id: int, video_ids: Optional[List[int]] = None) -> bool:
        """Clear continue watching list"""
        try:
            cache_key = f"continue_watching:{user_id}"
            
            if video_ids:
                # Remove specific videos
                cached_data = await self.redis_client.get(cache_key)
                if cached_data:
                    continue_watching_data = json.loads(cached_data)
                    filtered_data = [item for item in continue_watching_data if item['video_id'] not in video_ids]
                    await self.redis_client.setex(cache_key, 86400 * 7, json.dumps(filtered_data))
            else:
                # Clear all
                await self.redis_client.delete(cache_key)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear continue watching: {e}")
            return False
    
    async def _save_watch_session(self, session: WatchSession):
        """Save watch session to Redis"""
        try:
            session_key = f"session:{session.user_id}:{session.session_id}"
            session_data = {
                'session_id': session.session_id,
                'user_id': session.user_id,
                'video_id': session.video_id,
                'started_at': session.started_at.isoformat(),
                'ended_at': session.ended_at.isoformat() if session.ended_at else None,
                'watch_duration': session.watch_duration,
                'video_duration': session.video_duration,
                'progress_percent': session.progress_percent,
                'session_type': session.session_type.value,
                'source_context': session.source_context,
                'device_info': session.device_info,
                'quality_watched': session.quality_watched,
                'is_completed': session.is_completed
            }
            
            # Store for 7 days
            await self.redis_client.setex(session_key, 86400 * 7, json.dumps(session_data))
            
        except Exception as e:
            logger.error(f"Failed to save watch session: {e}")
    
    async def _load_watch_session(self, session_id: str) -> Optional[WatchSession]:
        """Load watch session from Redis"""
        try:
            # Try different user patterns since we might not know the user_id
            pattern = f"session:*:{session_id}"
            keys = await self.redis_client.keys(pattern)
            
            if not keys:
                return None
            
            session_data = await self.redis_client.get(keys[0])
            if not session_data:
                return None
            
            data = json.loads(session_data)
            
            session = WatchSession(
                session_id=data['session_id'],
                user_id=data.get('user_id'),
                video_id=data['video_id'],
                started_at=datetime.fromisoformat(data['started_at']),
                ended_at=datetime.fromisoformat(data['ended_at']) if data.get('ended_at') else None,
                watch_duration=data['watch_duration'],
                video_duration=data['video_duration'],
                progress_percent=data['progress_percent'],
                session_type=SessionType(data['session_type']),
                source_context=data.get('source_context'),
                device_info=data.get('device_info'),
                quality_watched=data.get('quality_watched'),
                is_completed=data['is_completed']
            )
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to load watch session: {e}")
            return None
    
    async def _update_video_history(self, session: WatchSession):
        """Update video watch history"""
        try:
            cache_key = f"video_history:{session.video_id}" + (f":{session.user_id}" if session.user_id else "")
            
            # Load existing history
            existing_history = await self.get_video_watch_history(session.video_id, session.user_id)
            
            if existing_history:
                # Update existing history
                existing_history.total_watch_time += session.watch_duration
                existing_history.total_sessions += 1
                existing_history.last_watched = session.started_at
                
                if session.is_completed:
                    existing_history.completion_count += 1
                    existing_history.watch_status = WatchStatus.COMPLETED
                
                existing_history.current_progress_percent = session.progress_percent
                
                # Add session to history
                existing_history.sessions.append(session)
                
                # Keep only recent sessions to limit memory usage
                existing_history.sessions = sorted(existing_history.sessions, key=lambda x: x.started_at, reverse=True)[:10]
                
            else:
                # Create new history
                existing_history = VideoWatchHistory(
                    video_id=session.video_id,
                    total_watch_time=session.watch_duration,
                    total_sessions=1,
                    first_watched=session.started_at,
                    last_watched=session.started_at,
                    completion_count=1 if session.is_completed else 0,
                    current_progress_percent=session.progress_percent,
                    watch_status=WatchStatus.COMPLETED if session.is_completed else (WatchStatus.STARTED if session.progress_percent > 5 else WatchStatus.NOT_STARTED),
                    sessions=[session]
                )
            
            # Save updated history
            history_data = {
                'video_id': existing_history.video_id,
                'total_watch_time': existing_history.total_watch_time,
                'total_sessions': existing_history.total_sessions,
                'first_watched': existing_history.first_watched.isoformat(),
                'last_watched': existing_history.last_watched.isoformat(),
                'completion_count': existing_history.completion_count,
                'current_progress_percent': existing_history.current_progress_percent,
                'watch_status': existing_history.watch_status.value,
                'sessions': [
                    {
                        'session_id': s.session_id,
                        'user_id': s.user_id,
                        'video_id': s.video_id,
                        'started_at': s.started_at.isoformat(),
                        'ended_at': s.ended_at.isoformat() if s.ended_at else None,
                        'watch_duration': s.watch_duration,
                        'video_duration': s.video_duration,
                        'progress_percent': s.progress_percent,
                        'session_type': s.session_type.value,
                        'source_context': s.source_context,
                        'device_info': s.device_info,
                        'quality_watched': s.quality_watched,
                        'is_completed': s.is_completed
                    } for s in existing_history.sessions
                ],
                'favorite_marked_at': existing_history.favorite_marked_at.isoformat() if existing_history.favorite_marked_at else None
            }
            
            await self.redis_client.setex(cache_key, 86400 * self.history_retention_days, json.dumps(history_data))
            
        except Exception as e:
            logger.error(f"Failed to update video history: {e}")
    
    async def _add_to_continue_watching(self, session: WatchSession):
        """Add video to continue watching list"""
        try:
            if not session.user_id:
                return
            
            cache_key = f"continue_watching:{session.user_id}"
            
            # Load existing continue watching data
            cached_data = await self.redis_client.get(cache_key)
            continue_watching_data = json.loads(cached_data) if cached_data else []
            
            # Remove existing entry for this video
            continue_watching_data = [item for item in continue_watching_data if item['video_id'] != session.video_id]
            
            # Add new entry
            new_item = {
                'video_id': session.video_id,
                'progress_percent': session.progress_percent,
                'last_watched': session.started_at.isoformat(),
                'session_type': session.session_type.value,
                'source_context': session.source_context
            }
            
            continue_watching_data.insert(0, new_item)
            
            # Keep only the most recent items
            continue_watching_data = continue_watching_data[:self.continue_watching_limit]
            
            # Save updated list
            await self.redis_client.setex(cache_key, 86400 * 7, json.dumps(continue_watching_data))
            
        except Exception as e:
            logger.error(f"Failed to add to continue watching: {e}")
    
    async def _remove_from_continue_watching(self, video_id: int, user_id: Optional[int]):
        """Remove video from continue watching list"""
        try:
            if not user_id:
                return
            
            cache_key = f"continue_watching:{user_id}"
            
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                continue_watching_data = json.loads(cached_data)
                filtered_data = [item for item in continue_watching_data if item['video_id'] != video_id]
                
                await self.redis_client.setex(cache_key, 86400 * 7, json.dumps(filtered_data))
            
        except Exception as e:
            logger.error(f"Failed to remove from continue watching: {e}")
    
    async def _increment_video_view_count(self, video_id: int):
        """Increment video view count in database"""
        try:
            async with get_async_session() as session:
                video_query = select(Video).where(Video.id == video_id)
                result = await session.execute(video_query)
                video = result.scalar_one_or_none()
                
                if video:
                    video.view_count = (video.view_count or 0) + 1
                    video.last_watched = datetime.now()
                    
                    await session.commit()
            
        except Exception as e:
            logger.error(f"Failed to increment view count for video {video_id}: {e}")
    
    async def _calculate_watch_streak(self, user_id: int) -> int:
        """Calculate current watch streak in days"""
        try:
            # Get user's recent sessions
            pattern = f"session:{user_id}:*"
            session_keys = await self.redis_client.keys(pattern)
            
            if not session_keys:
                return 0
            
            # Get session dates
            session_dates = set()
            for key in session_keys:
                session_data = await self.redis_client.get(key)
                if session_data:
                    session_info = json.loads(session_data)
                    session_date = datetime.fromisoformat(session_info['started_at']).date()
                    session_dates.add(session_date)
            
            if not session_dates:
                return 0
            
            # Calculate streak
            sorted_dates = sorted(session_dates, reverse=True)
            current_date = datetime.now().date()
            
            streak = 0
            for date in sorted_dates:
                if date == current_date - timedelta(days=streak):
                    streak += 1
                else:
                    break
            
            return streak
            
        except Exception as e:
            logger.error(f"Failed to calculate watch streak: {e}")
            return 0

# Global service instance
_watch_history_service = None

async def get_watch_history_service(config: Optional[Dict] = None) -> WatchHistoryService:
    """Get global watch history service instance"""
    global _watch_history_service
    
    if _watch_history_service is None:
        _watch_history_service = WatchHistoryService(config)
        await _watch_history_service.initialize()
    
    return _watch_history_service