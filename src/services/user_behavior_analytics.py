"""
User Behavior Analytics Service - Phase 3 Week 27
Track and analyze user interactions, behavior patterns, and engagement metrics for music video management
"""

import asyncio
import hashlib
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.user_behavior_analytics")


class UserActionType(Enum):
    """Types of user actions to track"""

    PAGE_VIEW = "page_view"
    VIDEO_SEARCH = "video_search"
    VIDEO_PLAY = "video_play"
    VIDEO_PAUSE = "video_pause"
    VIDEO_STOP = "video_stop"
    VIDEO_SEEK = "video_seek"
    VIDEO_DOWNLOAD = "video_download"
    PLAYLIST_CREATE = "playlist_create"
    PLAYLIST_ADD = "playlist_add"
    ARTIST_FOLLOW = "artist_follow"
    SEARCH_QUERY = "search_query"
    FILTER_APPLY = "filter_apply"
    SETTINGS_CHANGE = "settings_change"
    LOGIN = "login"
    LOGOUT = "logout"
    ERROR_ENCOUNTERED = "error_encountered"


class SessionStatus(Enum):
    """User session status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"


@dataclass
class UserAction:
    """Individual user action event"""

    action_id: str
    user_id: str
    session_id: str
    action_type: UserActionType
    timestamp: float
    page_url: str
    user_agent: str
    ip_address: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "action_type": self.action_type.value,
            "timestamp": self.timestamp,
            "page_url": self.page_url,
            "user_agent": self.user_agent,
            "ip_address": self.ip_address,
            "metadata": self.metadata,
            "duration_ms": self.duration_ms,
        }


@dataclass
class UserSession:
    """User session data"""

    session_id: str
    user_id: str
    start_time: float
    last_activity: float
    status: SessionStatus
    pages_visited: List[str] = field(default_factory=list)
    actions_count: int = 0
    total_duration_ms: int = 0
    device_info: Dict[str, str] = field(default_factory=dict)
    referrer: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "start_time": self.start_time,
            "last_activity": self.last_activity,
            "status": self.status.value,
            "pages_visited": self.pages_visited,
            "actions_count": self.actions_count,
            "total_duration_ms": self.total_duration_ms,
            "device_info": self.device_info,
            "referrer": self.referrer,
            "duration_minutes": (self.last_activity - self.start_time) / 60,
        }


@dataclass
class UserEngagementMetrics:
    """User engagement analysis"""

    user_id: str
    analysis_period: str
    total_sessions: int
    total_time_minutes: float
    avg_session_duration_minutes: float
    pages_per_session: float
    videos_played: int
    videos_downloaded: int
    searches_performed: int
    most_active_hours: List[int]
    favorite_content_types: Dict[str, int]
    engagement_score: float
    last_activity: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "analysis_period": self.analysis_period,
            "total_sessions": self.total_sessions,
            "total_time_minutes": self.total_time_minutes,
            "avg_session_duration_minutes": self.avg_session_duration_minutes,
            "pages_per_session": self.pages_per_session,
            "videos_played": self.videos_played,
            "videos_downloaded": self.videos_downloaded,
            "searches_performed": self.searches_performed,
            "most_active_hours": self.most_active_hours,
            "favorite_content_types": self.favorite_content_types,
            "engagement_score": self.engagement_score,
            "last_activity": self.last_activity,
        }


class UserBehaviorAnalytics:
    """Advanced user behavior tracking and analysis service"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize user behavior analytics"""
        self.config = config or {
            "session_timeout_minutes": 30,
            "max_actions_buffer": 10000,
            "analysis_interval_minutes": 5,
            "engagement_score_weights": {
                "session_count": 0.2,
                "total_time": 0.25,
                "video_interactions": 0.3,
                "search_activity": 0.15,
                "content_creation": 0.1,
            },
            "cache_ttl": 3600,
            "enable_real_time_processing": True,
        }

        # Data storage
        self.actions_buffer = deque(maxlen=self.config["max_actions_buffer"])
        self.active_sessions: Dict[str, UserSession] = {}
        self.user_metrics: Dict[str, UserEngagementMetrics] = {}

        # Analytics processing
        self.processing_active = True
        self.last_analysis_time = time.time()

        # Performance tracking
        self.stats = {
            "actions_tracked": 0,
            "sessions_created": 0,
            "analyses_completed": 0,
            "total_processing_time": 0.0,
            "active_users_last_hour": 0,
        }

        # Start background processing
        if self.config["enable_real_time_processing"]:
            self._start_background_processing()

        logger.info("👤 User behavior analytics service initialized")

    def _start_background_processing(self):
        """Start background analytics processing"""
        asyncio.create_task(self._analysis_loop())
        asyncio.create_task(self._session_cleanup_loop())

    async def _analysis_loop(self):
        """Background analytics processing loop"""
        while self.processing_active:
            try:
                await asyncio.sleep(self.config["analysis_interval_minutes"] * 60)
                await self._process_analytics()
            except Exception as e:
                logger.error(f"Analytics processing error: {e}")

    async def _session_cleanup_loop(self):
        """Background session cleanup loop"""
        while self.processing_active:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Session cleanup error: {e}")

    async def track_user_action(
        self,
        user_id: str,
        action_type: UserActionType,
        page_url: str,
        user_agent: str,
        session_id: Optional[str] = None,
        ip_address: str = "",
        metadata: Dict[str, Any] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        """
        Track a user action event

        Args:
            user_id: User identifier
            action_type: Type of action performed
            page_url: URL where action occurred
            user_agent: User's browser/client info
            session_id: Optional session identifier
            ip_address: User's IP address
            metadata: Additional action-specific data
            duration_ms: Action duration in milliseconds

        Returns:
            Action ID for tracking
        """
        try:
            current_time = time.time()

            # Generate session ID if not provided
            if not session_id:
                session_id = self._generate_session_id(user_id, current_time)

            # Create or update session
            await self._update_user_session(
                user_id, session_id, page_url, user_agent, current_time
            )

            # Generate action ID
            action_id = f"action_{hashlib.md5(f'{user_id}_{session_id}_{current_time}'.encode()).hexdigest()[:16]}"

            # Create action event
            action = UserAction(
                action_id=action_id,
                user_id=user_id,
                session_id=session_id,
                action_type=action_type,
                timestamp=current_time,
                page_url=page_url,
                user_agent=user_agent,
                ip_address=ip_address,
                metadata=metadata or {},
                duration_ms=duration_ms,
            )

            # Store action
            self.actions_buffer.append(action)
            self.stats["actions_tracked"] += 1

            # Cache action for real-time access
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.USER_DATA,
                f"user_action_{action_id}",
                action.to_dict(),
                ttl=self.config["cache_ttl"],
            )

            logger.debug(f"👤 Tracked {action_type.value} action for user {user_id}")
            return action_id

        except Exception as e:
            logger.error(f"Failed to track user action: {e}")
            return ""

    def _generate_session_id(self, user_id: str, timestamp: float) -> str:
        """Generate unique session ID"""
        session_data = f"{user_id}_{int(timestamp // 1800)}"  # 30-minute buckets
        return f"session_{hashlib.md5(session_data.encode()).hexdigest()[:16]}"

    async def _update_user_session(
        self,
        user_id: str,
        session_id: str,
        page_url: str,
        user_agent: str,
        timestamp: float,
    ):
        """Update user session information"""
        if session_id not in self.active_sessions:
            # Create new session
            session = UserSession(
                session_id=session_id,
                user_id=user_id,
                start_time=timestamp,
                last_activity=timestamp,
                status=SessionStatus.ACTIVE,
                device_info=self._parse_user_agent(user_agent),
            )

            self.active_sessions[session_id] = session
            self.stats["sessions_created"] += 1
            logger.debug(f"👤 Created new session {session_id} for user {user_id}")
        else:
            # Update existing session
            session = self.active_sessions[session_id]
            session.last_activity = timestamp
            session.status = SessionStatus.ACTIVE

        # Update session data
        session = self.active_sessions[session_id]
        session.actions_count += 1

        if page_url not in session.pages_visited:
            session.pages_visited.append(page_url)

    def _parse_user_agent(self, user_agent: str) -> Dict[str, str]:
        """Parse user agent string for device info"""
        device_info = {"browser": "unknown", "os": "unknown", "device_type": "unknown"}

        user_agent = user_agent.lower()

        # Browser detection
        if "chrome" in user_agent:
            device_info["browser"] = "chrome"
        elif "firefox" in user_agent:
            device_info["browser"] = "firefox"
        elif "safari" in user_agent:
            device_info["browser"] = "safari"
        elif "edge" in user_agent:
            device_info["browser"] = "edge"

        # OS detection
        if "windows" in user_agent:
            device_info["os"] = "windows"
        elif "mac" in user_agent:
            device_info["os"] = "macos"
        elif "linux" in user_agent:
            device_info["os"] = "linux"
        elif "android" in user_agent:
            device_info["os"] = "android"
        elif "ios" in user_agent:
            device_info["os"] = "ios"

        # Device type detection
        if "mobile" in user_agent or "android" in user_agent or "ios" in user_agent:
            device_info["device_type"] = "mobile"
        elif "tablet" in user_agent or "ipad" in user_agent:
            device_info["device_type"] = "tablet"
        else:
            device_info["device_type"] = "desktop"

        return device_info

    async def _cleanup_expired_sessions(self):
        """Clean up expired user sessions"""
        current_time = time.time()
        timeout_seconds = self.config["session_timeout_minutes"] * 60

        expired_sessions = []
        for session_id, session in self.active_sessions.items():
            if current_time - session.last_activity > timeout_seconds:
                session.status = SessionStatus.EXPIRED
                expired_sessions.append(session_id)

        # Archive expired sessions
        for session_id in expired_sessions:
            session = self.active_sessions[session_id]
            session.total_duration_ms = int(
                (session.last_activity - session.start_time) * 1000
            )

            # Cache expired session
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.USER_DATA,
                f"expired_session_{session_id}",
                session.to_dict(),
                ttl=86400,  # 24 hours
            )

            del self.active_sessions[session_id]

        if expired_sessions:
            logger.info(f"👤 Cleaned up {len(expired_sessions)} expired sessions")

    async def _process_analytics(self):
        """Process analytics and generate user engagement metrics"""
        start_time = time.time()

        try:
            # Get unique users from recent actions
            recent_users = set()
            current_time = time.time()
            hour_ago = current_time - 3600

            for action in self.actions_buffer:
                if action.timestamp >= hour_ago:
                    recent_users.add(action.user_id)

            self.stats["active_users_last_hour"] = len(recent_users)

            # Generate engagement metrics for active users
            for user_id in recent_users:
                await self._calculate_user_engagement(user_id)

            # Update processing stats
            processing_time = time.time() - start_time
            self.stats["analyses_completed"] += 1
            self.stats["total_processing_time"] += processing_time
            self.last_analysis_time = current_time

            # Track performance
            await track_media_processing_time("user_behavior_analysis", processing_time)

            logger.info(
                f"👤 Processed analytics for {len(recent_users)} users in {processing_time:.2f}s"
            )

        except Exception as e:
            logger.error(f"Analytics processing failed: {e}")

    async def _calculate_user_engagement(self, user_id: str) -> UserEngagementMetrics:
        """Calculate comprehensive user engagement metrics"""
        try:
            current_time = time.time()
            week_ago = current_time - (7 * 24 * 3600)  # 7 days

            # Filter user actions for the last week
            user_actions = [
                action
                for action in self.actions_buffer
                if action.user_id == user_id and action.timestamp >= week_ago
            ]

            if not user_actions:
                return None

            # Calculate basic metrics
            sessions = set(action.session_id for action in user_actions)
            total_sessions = len(sessions)

            # Calculate session durations
            session_durations = {}
            pages_per_session = {}

            for session_id in sessions:
                session_actions = [
                    a for a in user_actions if a.session_id == session_id
                ]
                if len(session_actions) > 1:
                    start_time = min(a.timestamp for a in session_actions)
                    end_time = max(a.timestamp for a in session_actions)
                    session_durations[session_id] = (
                        end_time - start_time
                    ) / 60  # minutes
                else:
                    session_durations[session_id] = (
                        1.0  # Default 1 minute for single-action sessions
                    )

                # Pages per session
                pages = set(a.page_url for a in session_actions)
                pages_per_session[session_id] = len(pages)

            total_time_minutes = sum(session_durations.values())
            avg_session_duration = (
                total_time_minutes / total_sessions if total_sessions > 0 else 0
            )
            avg_pages_per_session = (
                sum(pages_per_session.values()) / len(pages_per_session)
                if pages_per_session
                else 0
            )

            # Count specific action types
            action_counts = defaultdict(int)
            for action in user_actions:
                action_counts[action.action_type] += 1

            videos_played = action_counts[UserActionType.VIDEO_PLAY]
            videos_downloaded = action_counts[UserActionType.VIDEO_DOWNLOAD]
            searches_performed = action_counts[UserActionType.SEARCH_QUERY]

            # Most active hours
            hours = [
                int(datetime.fromtimestamp(a.timestamp).hour) for a in user_actions
            ]
            hour_counts = defaultdict(int)
            for hour in hours:
                hour_counts[hour] += 1

            most_active_hours = sorted(
                hour_counts.keys(), key=lambda h: hour_counts[h], reverse=True
            )[:3]

            # Favorite content types (from metadata)
            content_types = defaultdict(int)
            for action in user_actions:
                if "content_type" in action.metadata:
                    content_types[action.metadata["content_type"]] += 1

            # Calculate engagement score
            weights = self.config["engagement_score_weights"]
            engagement_score = (
                min(total_sessions / 10, 1.0) * weights["session_count"] * 100
                + min(total_time_minutes / 60, 1.0) * weights["total_time"] * 100
                + min((videos_played + videos_downloaded) / 20, 1.0)
                * weights["video_interactions"]
                * 100
                + min(searches_performed / 10, 1.0) * weights["search_activity"] * 100
                + min(action_counts[UserActionType.PLAYLIST_CREATE] / 5, 1.0)
                * weights["content_creation"]
                * 100
            )

            # Create engagement metrics
            metrics = UserEngagementMetrics(
                user_id=user_id,
                analysis_period="7_days",
                total_sessions=total_sessions,
                total_time_minutes=total_time_minutes,
                avg_session_duration_minutes=avg_session_duration,
                pages_per_session=avg_pages_per_session,
                videos_played=videos_played,
                videos_downloaded=videos_downloaded,
                searches_performed=searches_performed,
                most_active_hours=most_active_hours,
                favorite_content_types=dict(content_types),
                engagement_score=round(engagement_score, 1),
                last_activity=max(a.timestamp for a in user_actions),
            )

            # Store metrics
            self.user_metrics[user_id] = metrics

            # Cache metrics
            cache_manager = await get_media_cache_manager()
            await cache_manager.set(
                CacheType.USER_DATA,
                f"user_engagement_{user_id}",
                metrics.to_dict(),
                ttl=self.config["cache_ttl"],
            )

            return metrics

        except Exception as e:
            logger.error(f"Failed to calculate user engagement for {user_id}: {e}")
            return None

    async def get_user_engagement_metrics(
        self, user_id: str
    ) -> Optional[UserEngagementMetrics]:
        """Get engagement metrics for a specific user"""
        # Check cache first
        cache_manager = await get_media_cache_manager()
        cached_metrics = await cache_manager.get(
            CacheType.USER_DATA, f"user_engagement_{user_id}"
        )

        if cached_metrics:
            return UserEngagementMetrics(**cached_metrics)

        # Calculate fresh metrics
        return await self._calculate_user_engagement(user_id)

    async def get_user_session_info(self, session_id: str) -> Optional[UserSession]:
        """Get information about a user session"""
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]

        # Check archived sessions
        cache_manager = await get_media_cache_manager()
        cached_session = await cache_manager.get(
            CacheType.USER_DATA, f"expired_session_{session_id}"
        )

        if cached_session:
            session_data = cached_session
            session_data["status"] = SessionStatus(session_data["status"])
            return UserSession(**session_data)

        return None

    async def get_user_actions(
        self,
        user_id: str,
        action_type: Optional[UserActionType] = None,
        hours: int = 24,
    ) -> List[UserAction]:
        """Get user actions for specified time period"""
        cutoff_time = time.time() - (hours * 3600)

        actions = []
        for action in self.actions_buffer:
            if (
                action.user_id == user_id
                and action.timestamp >= cutoff_time
                and (action_type is None or action.action_type == action_type)
            ):
                actions.append(action)

        return sorted(actions, key=lambda a: a.timestamp, reverse=True)

    async def get_popular_content(self, hours: int = 24) -> Dict[str, Any]:
        """Get popular content based on user interactions"""
        cutoff_time = time.time() - (hours * 3600)

        # Count video plays and downloads
        video_interactions = defaultdict(int)
        search_queries = defaultdict(int)
        popular_pages = defaultdict(int)

        for action in self.actions_buffer:
            if action.timestamp >= cutoff_time:
                # Track video interactions
                if action.action_type in [
                    UserActionType.VIDEO_PLAY,
                    UserActionType.VIDEO_DOWNLOAD,
                ]:
                    if "video_id" in action.metadata:
                        video_interactions[action.metadata["video_id"]] += 1

                # Track search queries
                if action.action_type == UserActionType.SEARCH_QUERY:
                    if "query" in action.metadata:
                        search_queries[action.metadata["query"]] += 1

                # Track popular pages
                popular_pages[action.page_url] += 1

        # Get top items
        top_videos = sorted(
            video_interactions.items(), key=lambda x: x[1], reverse=True
        )[:10]
        top_searches = sorted(search_queries.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]
        top_pages = sorted(popular_pages.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "analysis_period_hours": hours,
            "popular_videos": [
                {"video_id": vid, "interactions": count} for vid, count in top_videos
            ],
            "popular_searches": [
                {"query": query, "count": count} for query, count in top_searches
            ],
            "popular_pages": [
                {"page": page, "views": count} for page, count in top_pages
            ],
            "total_interactions": len(
                [a for a in self.actions_buffer if a.timestamp >= cutoff_time]
            ),
        }

    async def get_analytics_summary(self) -> Dict[str, Any]:
        """Get comprehensive analytics summary"""
        try:
            current_time = time.time()

            # Active users in different time periods
            hour_ago = current_time - 3600
            day_ago = current_time - (24 * 3600)
            week_ago = current_time - (7 * 24 * 3600)

            active_users_1h = len(
                set(a.user_id for a in self.actions_buffer if a.timestamp >= hour_ago)
            )
            active_users_24h = len(
                set(a.user_id for a in self.actions_buffer if a.timestamp >= day_ago)
            )
            active_users_7d = len(
                set(a.user_id for a in self.actions_buffer if a.timestamp >= week_ago)
            )

            # Action distribution
            action_counts = defaultdict(int)
            for action in self.actions_buffer:
                if action.timestamp >= day_ago:
                    action_counts[action.action_type.value] += 1

            return {
                "timestamp": current_time,
                "active_users": {
                    "last_hour": active_users_1h,
                    "last_24_hours": active_users_24h,
                    "last_7_days": active_users_7d,
                },
                "active_sessions": len(self.active_sessions),
                "total_actions_tracked": self.stats["actions_tracked"],
                "action_distribution_24h": dict(action_counts),
                "processing_stats": self.stats,
                "avg_engagement_score": self._calculate_average_engagement_score(),
                "service_health": {
                    "processing_active": self.processing_active,
                    "last_analysis": self.last_analysis_time,
                    "buffer_utilization": len(self.actions_buffer)
                    / self.config["max_actions_buffer"],
                },
            }

        except Exception as e:
            logger.error(f"Failed to generate analytics summary: {e}")
            return {"error": str(e)}

    def _calculate_average_engagement_score(self) -> float:
        """Calculate average engagement score across all users"""
        if not self.user_metrics:
            return 0.0

        scores = [metrics.engagement_score for metrics in self.user_metrics.values()]
        return sum(scores) / len(scores) if scores else 0.0

    async def generate_user_report(self, user_id: str) -> Dict[str, Any]:
        """Generate comprehensive user behavior report"""
        try:
            engagement_metrics = await self.get_user_engagement_metrics(user_id)
            recent_actions = await self.get_user_actions(
                user_id, hours=168
            )  # Last week

            # Active sessions for this user
            user_sessions = [
                session.to_dict()
                for session in self.active_sessions.values()
                if session.user_id == user_id
            ]

            return {
                "user_id": user_id,
                "report_generated": time.time(),
                "engagement_metrics": (
                    engagement_metrics.to_dict() if engagement_metrics else None
                ),
                "recent_activity": {
                    "total_actions_7d": len(recent_actions),
                    "action_breakdown": self._count_actions_by_type(recent_actions),
                    "most_recent_action": (
                        recent_actions[0].to_dict() if recent_actions else None
                    ),
                },
                "active_sessions": user_sessions,
                "behavior_insights": self._generate_user_insights(
                    user_id, engagement_metrics, recent_actions
                ),
            }

        except Exception as e:
            logger.error(f"Failed to generate user report for {user_id}: {e}")
            return {"error": str(e)}

    def _count_actions_by_type(self, actions: List[UserAction]) -> Dict[str, int]:
        """Count actions by type"""
        counts = defaultdict(int)
        for action in actions:
            counts[action.action_type.value] += 1
        return dict(counts)

    def _generate_user_insights(
        self,
        user_id: str,
        engagement_metrics: Optional[UserEngagementMetrics],
        recent_actions: List[UserAction],
    ) -> List[str]:
        """Generate behavioral insights for user"""
        insights = []

        if not engagement_metrics or not recent_actions:
            return ["Insufficient data for insights"]

        # Engagement level
        if engagement_metrics.engagement_score >= 75:
            insights.append("Highly engaged user with strong interaction patterns")
        elif engagement_metrics.engagement_score >= 50:
            insights.append("Moderately engaged user with regular activity")
        else:
            insights.append(
                "Low engagement - consider targeted re-engagement strategies"
            )

        # Session behavior
        if engagement_metrics.avg_session_duration_minutes > 15:
            insights.append(
                "Extended session durations indicate strong content interest"
            )
        elif engagement_metrics.avg_session_duration_minutes < 5:
            insights.append("Short sessions suggest quick browsing behavior")

        # Content preferences
        if engagement_metrics.videos_played > 10:
            insights.append("Active video consumer - prioritize video recommendations")

        if engagement_metrics.searches_performed > 5:
            insights.append(
                "Frequent searcher - ensure search functionality is optimized"
            )

        # Activity patterns
        if engagement_metrics.most_active_hours:
            peak_hour = engagement_metrics.most_active_hours[0]
            if 9 <= peak_hour <= 17:
                insights.append("Most active during business hours")
            elif 18 <= peak_hour <= 23:
                insights.append("Most active during evening hours")
            else:
                insights.append("Most active during off-peak hours")

        return insights

    async def get_service_statistics(self) -> Dict[str, Any]:
        """Get user behavior analytics service statistics"""
        try:
            return {
                "service": "User Behavior Analytics",
                "status": "active" if self.processing_active else "inactive",
                "stats": self.stats,
                "configuration": self.config,
                "data_status": {
                    "actions_buffer_size": len(self.actions_buffer),
                    "active_sessions": len(self.active_sessions),
                    "tracked_users": len(self.user_metrics),
                    "buffer_utilization_percent": (
                        len(self.actions_buffer) / self.config["max_actions_buffer"]
                    )
                    * 100,
                },
                "capabilities": {
                    "real_time_tracking": True,
                    "session_management": True,
                    "engagement_analysis": True,
                    "behavior_insights": True,
                    "popular_content_analysis": True,
                },
            }
        except Exception as e:
            logger.error(f"Failed to get service statistics: {e}")
            return {"service": "User Behavior Analytics", "error": str(e)}


# Global user behavior analytics service instance
_user_behavior_analytics: Optional[UserBehaviorAnalytics] = None


async def get_user_behavior_analytics(
    config: Optional[Dict[str, Any]] = None
) -> UserBehaviorAnalytics:
    """Get or create global user behavior analytics service instance"""
    global _user_behavior_analytics

    if _user_behavior_analytics is None:
        _user_behavior_analytics = UserBehaviorAnalytics(config)

    return _user_behavior_analytics


# Convenience functions for tracking common user actions
async def track_video_play(
    user_id: str, video_id: str, session_id: str, page_url: str, user_agent: str
):
    """Track video play action"""
    analytics = await get_user_behavior_analytics()
    return await analytics.track_user_action(
        user_id=user_id,
        action_type=UserActionType.VIDEO_PLAY,
        page_url=page_url,
        user_agent=user_agent,
        session_id=session_id,
        metadata={"video_id": video_id, "content_type": "music_video"},
    )


async def track_search_query(
    user_id: str,
    query: str,
    results_count: int,
    session_id: str,
    page_url: str,
    user_agent: str,
):
    """Track search query action"""
    analytics = await get_user_behavior_analytics()
    return await analytics.track_user_action(
        user_id=user_id,
        action_type=UserActionType.SEARCH_QUERY,
        page_url=page_url,
        user_agent=user_agent,
        session_id=session_id,
        metadata={"query": query, "results_count": results_count},
    )


async def track_page_view(
    user_id: str, page_url: str, user_agent: str, session_id: str, referrer: str = ""
):
    """Track page view action"""
    analytics = await get_user_behavior_analytics()
    return await analytics.track_user_action(
        user_id=user_id,
        action_type=UserActionType.PAGE_VIEW,
        page_url=page_url,
        user_agent=user_agent,
        session_id=session_id,
        metadata={"referrer": referrer},
    )
