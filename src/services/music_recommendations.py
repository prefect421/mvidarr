"""
MVidarr Music Recommendation Service - Phase 3 Week 25 (Revised)
API-based music video recommendations using MusicBrainz, Spotify, Last.fm, and other music services
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.services.allmusic_service import allmusic_service
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.musicbrainz_service import musicbrainz_service
from src.services.performance_monitor import track_media_processing_time
from src.services.spotify_service import spotify_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.music_recommendations")


# Async wrapper functions for sync services
async def get_spotify_service():
    """Get Spotify service instance (async wrapper for sync service)"""
    return spotify_service


async def get_allmusic_service():
    """Get AllMusic service instance (async wrapper for sync service)"""
    return allmusic_service


async def get_musicbrainz_service():
    """Get MusicBrainz service instance (async wrapper for sync service)"""
    return musicbrainz_service


class RecommendationType(Enum):
    """Types of music video recommendations"""

    SIMILAR_ARTISTS = "similar_artists"
    TRENDING_VIDEOS = "trending_videos"
    USER_BASED = "user_based"
    GENRE_BASED = "genre_based"
    DISCOVER_WEEKLY = "discover_weekly"
    NEW_RELEASES = "new_releases"
    TOP_CHARTS = "top_charts"
    RELATED_VIDEOS = "related_videos"


class RecommendationSource(Enum):
    """Sources for recommendation generation"""

    IMVDB = "imvdb"
    SPOTIFY = "spotify"
    LASTFM = "lastfm"
    ALLMUSIC = "allmusic"
    MUSICBRAINZ = "musicbrainz"
    USER_HISTORY = "user_history"
    COMBINED = "combined"


@dataclass
class RecommendationItem:
    """Individual music video recommendation"""

    video_id: str
    title: str
    artist_name: str
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    confidence: float = 0.0
    relevance_score: float = 0.0
    recommendation_type: RecommendationType = RecommendationType.SIMILAR_ARTISTS
    source: RecommendationSource = RecommendationSource.COMBINED
    reasons: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "artist_name": self.artist_name,
            "video_url": self.video_url,
            "thumbnail_url": self.thumbnail_url,
            "confidence": self.confidence,
            "relevance_score": self.relevance_score,
            "recommendation_type": self.recommendation_type.value,
            "source": self.source.value,
            "reasons": self.reasons,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass
class RecommendationRequest:
    """Request for music video recommendations"""

    user_id: Optional[str] = None
    artist_name: Optional[str] = None
    track_name: Optional[str] = None
    genre: Optional[str] = None
    recommendation_types: List[RecommendationType] = field(default_factory=list)
    max_recommendations: int = 20
    include_reasons: bool = True
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.recommendation_types:
            self.recommendation_types = [
                RecommendationType.SIMILAR_ARTISTS,
                RecommendationType.TRENDING_VIDEOS,
            ]


@dataclass
class RecommendationResult:
    """Result of recommendation generation"""

    recommendations: List[RecommendationItem]
    processing_time: float
    sources_used: List[str]
    cache_hit: bool = False
    total_found: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendations": [item.to_dict() for item in self.recommendations],
            "processing_time": self.processing_time,
            "sources_used": self.sources_used,
            "cache_hit": self.cache_hit,
            "total_found": self.total_found,
            "timestamp": self.timestamp,
        }


class MusicRecommendationService:
    """Music video recommendation service using music APIs"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize music recommendation service"""
        self.config = config or {
            "cache_ttl": 1800,  # 30 minutes
            "max_recommendations_per_source": 10,
            "similarity_threshold": 0.3,
            "enable_spotify": True,
            "enable_lastfm": True,
            "enable_allmusic": True,
            "enable_musicbrainz": True,
        }

        # Performance tracking
        self.recommendation_stats = {
            "total_requests": 0,
            "successful_recommendations": 0,
            "failed_recommendations": 0,
            "average_processing_time": 0.0,
            "cache_hits": 0,
            "source_usage": defaultdict(int),
        }

        logger.info("🎵 Music recommendation service initialized")

    async def get_recommendations(
        self, request: RecommendationRequest
    ) -> RecommendationResult:
        """Generate music video recommendations"""
        start_time = time.time()
        sources_used = []
        all_recommendations = []

        try:
            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"music_recommendations_{hash(str(request.__dict__))}"

            cached_result = await cache_manager.get(
                CacheType.BULK_OPERATION_RESULT, cache_key
            )
            if cached_result:
                self.recommendation_stats["cache_hits"] += 1
                cached_result["cache_hit"] = True
                return RecommendationResult(**cached_result)

            # Generate recommendations from different sources
            for rec_type in request.recommendation_types:
                if (
                    rec_type == RecommendationType.SIMILAR_ARTISTS
                    and request.artist_name
                ):
                    recs = await self._get_similar_artist_recommendations(
                        request.artist_name,
                        request.max_recommendations
                        // len(request.recommendation_types),
                    )
                    all_recommendations.extend(recs)
                    sources_used.extend(["spotify", "lastfm", "musicbrainz"])

                elif rec_type == RecommendationType.TRENDING_VIDEOS:
                    recs = await self._get_trending_video_recommendations(
                        request.max_recommendations // len(request.recommendation_types)
                    )
                    all_recommendations.extend(recs)

                elif rec_type == RecommendationType.USER_BASED and request.user_id:
                    recs = await self._get_user_based_recommendations(
                        request.user_id,
                        request.max_recommendations
                        // len(request.recommendation_types),
                    )
                    all_recommendations.extend(recs)

                elif rec_type == RecommendationType.GENRE_BASED and request.genre:
                    recs = await self._get_genre_based_recommendations(
                        request.genre,
                        request.max_recommendations
                        // len(request.recommendation_types),
                    )
                    all_recommendations.extend(recs)

                elif rec_type == RecommendationType.NEW_RELEASES:
                    recs = await self._get_new_release_recommendations(
                        request.max_recommendations // len(request.recommendation_types)
                    )
                    all_recommendations.extend(recs)

            # Remove duplicates and rank recommendations
            unique_recommendations = await self._deduplicate_and_rank(
                all_recommendations
            )

            # Limit to max recommendations
            final_recommendations = unique_recommendations[
                : request.max_recommendations
            ]

            processing_time = time.time() - start_time

            result = RecommendationResult(
                recommendations=final_recommendations,
                processing_time=processing_time,
                sources_used=list(set(sources_used)),
                total_found=len(all_recommendations),
            )

            # Cache result
            await cache_manager.set(
                CacheType.BULK_OPERATION_RESULT,
                cache_key,
                result.to_dict(),
                ttl=self.config["cache_ttl"],
            )

            # Update statistics
            self._update_recommendation_stats(result, sources_used)

            # Track performance
            await track_media_processing_time("music_recommendations", processing_time)

            logger.info(
                f"🎵 Generated {len(final_recommendations)} music recommendations"
            )
            return result

        except Exception as e:
            self.recommendation_stats["failed_recommendations"] += 1
            logger.error(f"❌ Music recommendation generation failed: {e}")

            return RecommendationResult(
                recommendations=[],
                processing_time=time.time() - start_time,
                sources_used=sources_used,
                total_found=0,
            )

    async def _get_similar_artist_recommendations(
        self, artist_name: str, max_count: int
    ) -> List[RecommendationItem]:
        """Get recommendations based on similar artists"""
        recommendations = []

        try:
            # Last.fm similar-artist video discovery removed: the old IMVDb
            # step attached videos for each similar artist via a bulk
            # per-artist search (search_artist_videos), which has no
            # MusicBrainz equivalent -- find_official_video() needs a
            # specific track name to verify a video against, and none is
            # known for a bare artist name.

            # Get Spotify recommendations
            if self.config["enable_spotify"] and len(recommendations) < max_count:
                try:
                    spotify_service = await get_spotify_service()
                    spotify_recs = await asyncio.to_thread(
                        spotify_service.get_recommendations,
                        seed_artists=[artist_name],
                        limit=max_count - len(recommendations),
                    )

                    for track in spotify_recs.get("tracks", [])[
                        : max_count - len(recommendations)
                    ]:
                        # Try to find the official music video via MusicBrainz
                        track_artist = track["artists"][0]["name"]
                        track_name = track["name"]

                        video_match = await asyncio.to_thread(
                            musicbrainz_service.find_official_video,
                            track_artist,
                            track_name,
                        )

                        if video_match:
                            recommendations.append(
                                RecommendationItem(
                                    video_id=str(video_match.get("recording_id", "")),
                                    title=track_name,
                                    artist_name=track_artist,
                                    video_url=video_match.get("video_url"),
                                    confidence=0.8,  # High confidence from Spotify
                                    relevance_score=track.get("popularity", 50) / 100.0,
                                    recommendation_type=RecommendationType.SIMILAR_ARTISTS,
                                    source=RecommendationSource.SPOTIFY,
                                    reasons=[
                                        f"Spotify recommends based on {artist_name}"
                                    ],
                                    metadata={
                                        "spotify_track_id": track["id"],
                                        "popularity": track.get("popularity", 0),
                                    },
                                )
                            )
                except Exception as e:
                    logger.warning(f"Spotify recommendations failed: {e}")

        except Exception as e:
            logger.error(f"❌ Similar artist recommendations failed: {e}")

        return recommendations[:max_count]

    async def _get_trending_video_recommendations(
        self, max_count: int
    ) -> List[RecommendationItem]:
        """Get trending music video recommendations

        Was IMVDb-only (get_trending_videos()) -- MusicBrainz has no
        trending/popularity data, so there's no replacement source. Returns
        empty until a trending-videos data source is built.
        """
        return []

    async def _get_user_based_recommendations(
        self, user_id: str, max_count: int
    ) -> List[RecommendationItem]:
        """Get user-based recommendations from listening history

        Was entirely dependent on IMVDb's bulk per-artist video search
        (search_artist_videos) to attach a video to each of the user's top
        Spotify artists -- MusicBrainz's find_official_video() needs a
        specific track name, which isn't known for a bare top-artist entry.
        Returns empty until a replacement bulk-discovery source is built.
        """
        return []

    async def _get_genre_based_recommendations(
        self, genre: str, max_count: int
    ) -> List[RecommendationItem]:
        """Get recommendations based on genre

        Was IMVDb-only (search_videos_by_genre()) -- MusicBrainz's
        find_official_video() takes a specific artist+track, not a genre,
        so there's no replacement source. Returns empty until a
        genre-based discovery source is built.
        """
        return []

    async def _get_new_release_recommendations(
        self, max_count: int
    ) -> List[RecommendationItem]:
        """Get new release recommendations

        Was entirely dependent on IMVDb's bulk per-artist video search
        (search_artist_videos) to attach a video to each Spotify new-release
        album's artist. MusicBrainz's find_official_video() needs a
        specific track name, not an album's artist, so there's no
        replacement here. Returns empty until a replacement bulk-discovery
        source is built.
        """
        return []

    async def _deduplicate_and_rank(
        self, recommendations: List[RecommendationItem]
    ) -> List[RecommendationItem]:
        """Remove duplicates and rank recommendations by relevance"""
        # Remove duplicates by video_id and title+artist combination
        unique_recommendations = {}

        for rec in recommendations:
            # Create unique key based on video_id or title+artist
            if rec.video_id and rec.video_id != "":
                key = f"id_{rec.video_id}"
            else:
                key = f"content_{rec.artist_name}_{rec.title}".lower().replace(" ", "_")

            if key not in unique_recommendations:
                unique_recommendations[key] = rec
            else:
                # If duplicate, combine confidence scores
                existing = unique_recommendations[key]
                combined_confidence = (existing.confidence + rec.confidence) / 2
                existing.confidence = combined_confidence
                existing.reasons.extend(rec.reasons)
                # Keep higher relevance score
                if rec.relevance_score > existing.relevance_score:
                    existing.relevance_score = rec.relevance_score

        # Sort by relevance score and confidence
        ranked_recs = sorted(
            unique_recommendations.values(),
            key=lambda x: (x.relevance_score * 0.7 + x.confidence * 0.3),
            reverse=True,
        )

        return ranked_recs

    def _update_recommendation_stats(
        self, result: RecommendationResult, sources_used: List[str]
    ):
        """Update recommendation statistics"""
        self.recommendation_stats["total_requests"] += 1
        self.recommendation_stats["successful_recommendations"] += 1

        # Update average processing time
        current_avg = self.recommendation_stats["average_processing_time"]
        total = self.recommendation_stats["total_requests"]
        new_avg = ((current_avg * (total - 1)) + result.processing_time) / total
        self.recommendation_stats["average_processing_time"] = new_avg

        # Update source usage stats
        for source in sources_used:
            self.recommendation_stats["source_usage"][source] += 1

    async def get_recommendation_statistics(self) -> Dict[str, Any]:
        """Get recommendation service performance statistics"""
        return {
            "recommendation_stats": self.recommendation_stats.copy(),
            "config": self.config.copy(),
            "enabled_sources": {
                "spotify": self.config["enable_spotify"],
                "lastfm": self.config["enable_lastfm"],
                "allmusic": self.config["enable_allmusic"],
                "musicbrainz": self.config["enable_musicbrainz"],
            },
        }


# Global music recommendation service instance
_music_recommendation_service: Optional[MusicRecommendationService] = None


async def get_music_recommendation_service(
    config: Optional[Dict[str, Any]] = None,
) -> MusicRecommendationService:
    """Get or create global music recommendation service instance"""
    global _music_recommendation_service

    if _music_recommendation_service is None:
        _music_recommendation_service = MusicRecommendationService(config)

    return _music_recommendation_service


# Convenience functions
async def get_music_recommendations(
    artist_name: Optional[str] = None,
    user_id: Optional[str] = None,
    genre: Optional[str] = None,
    recommendation_types: Optional[List[RecommendationType]] = None,
    max_recommendations: int = 20,
) -> RecommendationResult:
    """Get music video recommendations"""
    service = await get_music_recommendation_service()
    request = RecommendationRequest(
        artist_name=artist_name,
        user_id=user_id,
        genre=genre,
        recommendation_types=recommendation_types
        or [RecommendationType.SIMILAR_ARTISTS],
        max_recommendations=max_recommendations,
    )
    return await service.get_recommendations(request)


async def get_similar_artist_videos(
    artist_name: str, max_count: int = 10
) -> RecommendationResult:
    """Get music videos from similar artists"""
    return await get_music_recommendations(
        artist_name=artist_name,
        recommendation_types=[RecommendationType.SIMILAR_ARTISTS],
        max_recommendations=max_count,
    )


async def get_trending_music_videos(max_count: int = 20) -> RecommendationResult:
    """Get trending music videos"""
    return await get_music_recommendations(
        recommendation_types=[RecommendationType.TRENDING_VIDEOS],
        max_recommendations=max_count,
    )
