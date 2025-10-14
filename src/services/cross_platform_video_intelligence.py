"""
Cross-Platform Video Intelligence Service - Phase 3 Week 26
Intelligent service to correlate, analyze, and manage music videos across multiple platforms
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.services.imvdb_service import imvdb_service
from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.services.vevo_service import get_vevo_service
from src.services.vimeo_service import get_vimeo_service
from src.services.youtube_service import youtube_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.cross_platform_video_intelligence")


class Platform(Enum):
    """Supported video platforms"""

    YOUTUBE = "youtube"
    VEVO = "vevo"
    VIMEO = "vimeo"
    IMVDB = "imvdb"
    LOCAL = "local"


class VideoMatch(Enum):
    """Types of video matches across platforms"""

    IDENTICAL = "identical"  # Same exact video
    OFFICIAL_VERSION = "official"  # Official vs unofficial versions
    QUALITY_VARIANT = "quality"  # Different quality/resolution
    REMASTERED = "remastered"  # Remastered versions
    LIVE_VERSION = "live"  # Live vs studio versions
    REMIX = "remix"  # Remix/alternate versions
    COVER = "cover"  # Cover versions
    SIMILAR = "similar"  # Similar but different content


@dataclass
class CrossPlatformVideo:
    """Video representation across multiple platforms"""

    artist: str
    title: str
    primary_platform: Platform
    platforms: Dict[Platform, Dict[str, Any]] = field(default_factory=dict)
    best_version: Optional[Dict[str, Any]] = None
    quality_scores: Dict[Platform, float] = field(default_factory=dict)
    fingerprints: Dict[Platform, str] = field(default_factory=dict)
    match_confidence: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artist": self.artist,
            "title": self.title,
            "primary_platform": self.primary_platform.value,
            "platforms": {p.value: data for p, data in self.platforms.items()},
            "best_version": self.best_version,
            "quality_scores": {
                p.value: score for p, score in self.quality_scores.items()
            },
            "fingerprints": {p.value: fp for p, fp in self.fingerprints.items()},
            "match_confidence": self.match_confidence,
            "last_updated": self.last_updated,
        }


@dataclass
class VideoIntelligenceResult:
    """Result of cross-platform video intelligence analysis"""

    query_artist: str
    query_title: str
    total_videos_found: int
    platforms_searched: List[Platform]
    cross_platform_matches: List[CrossPlatformVideo]
    best_recommendations: List[Dict[str, Any]]
    processing_time: float
    cache_hit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_artist": self.query_artist,
            "query_title": self.query_title,
            "total_videos_found": self.total_videos_found,
            "platforms_searched": [p.value for p in self.platforms_searched],
            "cross_platform_matches": [
                v.to_dict() for v in self.cross_platform_matches
            ],
            "best_recommendations": self.best_recommendations,
            "processing_time": self.processing_time,
            "cache_hit": self.cache_hit,
        }


class CrossPlatformVideoIntelligence:
    """Intelligent cross-platform video analysis and correlation service"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize cross-platform video intelligence service"""
        self.config = config or {
            "similarity_threshold": 0.7,
            "quality_weight": 0.3,
            "official_weight": 0.4,
            "platform_priority": {
                Platform.VEVO: 1.0,  # Highest priority for official content
                Platform.YOUTUBE: 0.8,  # High priority, largest catalog
                Platform.VIMEO: 0.7,  # Good for independent artists
                Platform.IMVDB: 0.6,  # Metadata source
                Platform.LOCAL: 0.9,  # Local files get high priority
            },
            "cache_ttl": 3600,  # 1 hour
            "max_videos_per_platform": 10,
            "enable_quality_analysis": True,
            "enable_fingerprinting": True,
        }

        # Performance tracking
        self.stats = {
            "analyses_completed": 0,
            "cross_platform_matches_found": 0,
            "total_processing_time": 0.0,
            "platform_usage": {platform.value: 0 for platform in Platform},
            "match_types": {match.value: 0 for match in VideoMatch},
        }

        logger.info("🧠 Cross-platform video intelligence service initialized")

    async def correlate_videos_across_platforms(
        self, artist: str, title: str, platforms: Optional[List[Platform]] = None
    ) -> VideoIntelligenceResult:
        """
        Correlate and analyze videos across multiple platforms

        Args:
            artist: Artist name
            title: Song title
            platforms: List of platforms to search (default: all supported)

        Returns:
            VideoIntelligenceResult with cross-platform analysis
        """
        start_time = time.time()

        try:
            if not platforms:
                platforms = [
                    Platform.VEVO,
                    Platform.YOUTUBE,
                    Platform.VIMEO,
                    Platform.IMVDB,
                ]

            # Check cache first
            cache_manager = await get_media_cache_manager()
            cache_key = f"cross_platform_{hashlib.md5(f'{artist}_{title}'.encode()).hexdigest()}"

            cached_result = await cache_manager.get(
                CacheType.BULK_OPERATION_RESULT, cache_key
            )
            if cached_result:
                cached_result["cache_hit"] = True
                return VideoIntelligenceResult(**cached_result)

            logger.info(f"🧠 Analyzing videos across platforms for: {artist} - {title}")

            # Search all platforms concurrently
            platform_results = await self._search_all_platforms(
                artist, title, platforms
            )

            # Correlate videos across platforms
            cross_platform_matches = await self._correlate_platform_results(
                artist, title, platform_results
            )

            # Analyze and rank videos
            best_recommendations = await self._generate_best_recommendations(
                cross_platform_matches
            )

            # Calculate total videos found
            total_videos = sum(len(videos) for videos in platform_results.values())

            processing_time = time.time() - start_time

            # Create result
            result = VideoIntelligenceResult(
                query_artist=artist,
                query_title=title,
                total_videos_found=total_videos,
                platforms_searched=platforms,
                cross_platform_matches=cross_platform_matches,
                best_recommendations=best_recommendations,
                processing_time=processing_time,
            )

            # Cache result
            await cache_manager.set(
                CacheType.BULK_OPERATION_RESULT,
                cache_key,
                result.to_dict(),
                ttl=self.config["cache_ttl"],
            )

            # Update statistics
            self.stats["analyses_completed"] += 1
            self.stats["cross_platform_matches_found"] += len(cross_platform_matches)
            self.stats["total_processing_time"] += processing_time
            for platform in platforms:
                self.stats["platform_usage"][platform.value] += 1

            # Track performance
            await track_media_processing_time(
                "cross_platform_video_intelligence", processing_time
            )

            logger.info(
                f"🧠 Cross-platform analysis completed: {len(cross_platform_matches)} matches found "
                f"across {len(platforms)} platforms in {processing_time:.2f}s"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Cross-platform video analysis failed: {e}")
            return VideoIntelligenceResult(
                query_artist=artist,
                query_title=title,
                total_videos_found=0,
                platforms_searched=platforms or [],
                cross_platform_matches=[],
                best_recommendations=[],
                processing_time=time.time() - start_time,
            )

    async def _search_all_platforms(
        self, artist: str, title: str, platforms: List[Platform]
    ) -> Dict[Platform, List[Dict[str, Any]]]:
        """Search for videos across all specified platforms concurrently"""
        platform_results = {}

        # Create search tasks for all platforms
        search_tasks = []

        for platform in platforms:
            if platform == Platform.VEVO:
                task = self._search_vevo(artist, title)
            elif platform == Platform.YOUTUBE:
                task = self._search_youtube(artist, title)
            elif platform == Platform.VIMEO:
                task = self._search_vimeo(artist, title)
            elif platform == Platform.IMVDB:
                task = self._search_imvdb(artist, title)
            else:
                continue  # Skip unsupported platforms

            search_tasks.append((platform, task))

        # Execute all searches concurrently
        try:
            results = await asyncio.gather(
                *[task for _, task in search_tasks], return_exceptions=True
            )

            # Process results
            for i, (platform, _) in enumerate(search_tasks):
                result = results[i]
                if isinstance(result, Exception):
                    logger.warning(f"Search failed for {platform.value}: {result}")
                    platform_results[platform] = []
                else:
                    platform_results[platform] = result[
                        : self.config["max_videos_per_platform"]
                    ]

        except Exception as e:
            logger.error(f"Concurrent platform search failed: {e}")
            # Fallback to empty results
            for platform in platforms:
                platform_results[platform] = []

        return platform_results

    async def _search_vevo(self, artist: str, title: str) -> List[Dict[str, Any]]:
        """Search Vevo for official music videos"""
        try:
            vevo_service = await get_vevo_service()
            results = await vevo_service.search_official_music_videos(
                artist, title, limit=self.config["max_videos_per_platform"]
            )

            # Add platform identifier
            for result in results:
                result["platform"] = Platform.VEVO.value
                result["official"] = True

            return results

        except Exception as e:
            logger.error(f"Vevo search failed: {e}")
            return []

    async def _search_youtube(self, artist: str, title: str) -> List[Dict[str, Any]]:
        """Search YouTube for music videos"""
        try:
            # Use existing YouTube service
            query = f"{artist} {title} music video"
            results = await asyncio.to_thread(
                youtube_service.search_videos,
                query,
                max_results=self.config["max_videos_per_platform"],
            )

            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append(
                    {
                        "video_id": result.get("id", ""),
                        "title": result.get("title", ""),
                        "artist": artist,  # Assumed from search
                        "url": f"https://youtube.com/watch?v={result.get('id', '')}",
                        "thumbnail_url": result.get("thumbnail", ""),
                        "duration": result.get("duration", 0),
                        "view_count": result.get("view_count", 0),
                        "platform": Platform.YOUTUBE.value,
                        "channel": result.get("channel", ""),
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error(f"YouTube search failed: {e}")
            return []

    async def _search_vimeo(self, artist: str, title: str) -> List[Dict[str, Any]]:
        """Search Vimeo for independent music videos"""
        try:
            vimeo_service = await get_vimeo_service()
            results = await vimeo_service.search_independent_music_videos(
                artist, title, limit=self.config["max_videos_per_platform"]
            )

            # Add platform identifier
            for result in results:
                result["platform"] = Platform.VIMEO.value
                result["independent"] = True

            return results

        except Exception as e:
            logger.error(f"Vimeo search failed: {e}")
            return []

    async def _search_imvdb(self, artist: str, title: str) -> List[Dict[str, Any]]:
        """Search IMVDb for music video metadata"""
        try:
            # Use existing IMVDb service
            results = await asyncio.to_thread(
                imvdb_service.search_videos, artist, title
            )

            # Format results
            formatted_results = []
            for result in results[: self.config["max_videos_per_platform"]]:
                formatted_results.append(
                    {
                        "imvdb_id": result.get("id", ""),
                        "title": result.get("song_title", ""),
                        "artist": result.get("artist_name", artist),
                        "url": result.get("url", ""),
                        "thumbnail_url": result.get("image", {}).get("l", ""),
                        "year": result.get("year", ""),
                        "directors": result.get("directors", []),
                        "platform": Platform.IMVDB.value,
                        "metadata_source": True,
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error(f"IMVDb search failed: {e}")
            return []

    async def _correlate_platform_results(
        self,
        artist: str,
        title: str,
        platform_results: Dict[Platform, List[Dict[str, Any]]],
    ) -> List[CrossPlatformVideo]:
        """Correlate videos found across different platforms"""
        cross_platform_videos = []

        try:
            # Group videos by similarity
            all_videos = []
            for platform, videos in platform_results.items():
                for video in videos:
                    video["source_platform"] = platform
                    all_videos.append(video)

            # Find matches using title/artist similarity
            processed_videos = set()

            for video in all_videos:
                if id(video) in processed_videos:
                    continue

                # Create cross-platform video entry
                cross_platform_video = CrossPlatformVideo(
                    artist=artist,
                    title=title,
                    primary_platform=video["source_platform"],
                )

                # Add this video to the entry
                platform = video["source_platform"]
                cross_platform_video.platforms[platform] = video
                processed_videos.add(id(video))

                # Find similar videos on other platforms
                for other_video in all_videos:
                    if id(other_video) in processed_videos:
                        continue

                    if await self._videos_match(video, other_video):
                        other_platform = other_video["source_platform"]
                        cross_platform_video.platforms[other_platform] = other_video
                        processed_videos.add(id(other_video))

                # Calculate quality scores and determine best version
                await self._analyze_cross_platform_video(cross_platform_video)

                cross_platform_videos.append(cross_platform_video)

            # Sort by match confidence and quality
            cross_platform_videos.sort(
                key=lambda v: (len(v.platforms), v.match_confidence), reverse=True
            )

            return cross_platform_videos

        except Exception as e:
            logger.error(f"Video correlation failed: {e}")
            return []

    async def _videos_match(
        self, video1: Dict[str, Any], video2: Dict[str, Any]
    ) -> bool:
        """Determine if two videos from different platforms are the same content"""
        try:
            # Simple title similarity check
            title1 = video1.get("title", "").lower()
            title2 = video2.get("title", "").lower()

            # Clean titles
            for suffix in ["official video", "music video", "official", "hd", "4k"]:
                title1 = title1.replace(suffix, "").strip()
                title2 = title2.replace(suffix, "").strip()

            # Calculate word similarity
            words1 = set(title1.split())
            words2 = set(title2.split())

            if not words1 or not words2:
                return False

            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))

            similarity = intersection / union if union > 0 else 0

            return similarity >= self.config["similarity_threshold"]

        except Exception as e:
            logger.debug(f"Video matching failed: {e}")
            return False

    async def _analyze_cross_platform_video(
        self, cross_platform_video: CrossPlatformVideo
    ):
        """Analyze a cross-platform video to determine best version and scores"""
        try:
            platform_scores = {}
            best_video = None
            best_score = 0.0

            for platform, video_data in cross_platform_video.platforms.items():
                # Calculate platform-specific score
                score = self.config["platform_priority"].get(platform, 0.5)

                # Adjust for video-specific factors
                if video_data.get("official", False):
                    score += 0.3

                if video_data.get("hd_available", False):
                    score += 0.2

                if video_data.get("view_count", 0) > 1000000:  # Popular video
                    score += 0.1

                platform_scores[platform] = score

                # Check if this is the best version
                if score > best_score:
                    best_score = score
                    best_video = video_data.copy()
                    best_video["selected_platform"] = platform.value
                    best_video["selection_score"] = score

            cross_platform_video.quality_scores = platform_scores
            cross_platform_video.best_version = best_video
            cross_platform_video.match_confidence = min(1.0, best_score)

        except Exception as e:
            logger.error(f"Cross-platform video analysis failed: {e}")

    async def _generate_best_recommendations(
        self, cross_platform_matches: List[CrossPlatformVideo]
    ) -> List[Dict[str, Any]]:
        """Generate best video recommendations from cross-platform matches"""
        recommendations = []

        try:
            for match in cross_platform_matches[:10]:  # Top 10 matches
                if match.best_version:
                    recommendation = match.best_version.copy()
                    recommendation.update(
                        {
                            "cross_platform_match": True,
                            "available_platforms": list(match.platforms.keys()),
                            "platform_count": len(match.platforms),
                            "match_confidence": match.match_confidence,
                            "recommendation_score": match.match_confidence
                            * len(match.platforms),
                        }
                    )
                    recommendations.append(recommendation)

            # Sort by recommendation score
            recommendations.sort(
                key=lambda x: x.get("recommendation_score", 0), reverse=True
            )

            return recommendations

        except Exception as e:
            logger.error(f"Recommendation generation failed: {e}")
            return []

    async def identify_best_quality_version(
        self, video_matches: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Identify the best quality version from multiple video matches"""
        try:
            if not video_matches:
                return None

            best_video = None
            best_score = 0.0

            for video in video_matches:
                score = 0.0

                # Platform priority
                platform = video.get("platform", "")
                if platform == Platform.VEVO.value:
                    score += 1.0
                elif platform == Platform.YOUTUBE.value:
                    score += 0.8
                elif platform == Platform.VIMEO.value:
                    score += 0.7

                # Quality indicators
                if video.get("hd_available", False):
                    score += 0.3
                if video.get("4k_available", False):
                    score += 0.5
                if video.get("official", False):
                    score += 0.4

                # Popularity factor (normalized)
                view_count = video.get("view_count", 0)
                if view_count > 0:
                    score += min(0.3, view_count / 10000000)  # Max 0.3 for 10M+ views

                if score > best_score:
                    best_score = score
                    best_video = video.copy()
                    best_video["quality_score"] = score

            return best_video

        except Exception as e:
            logger.error(f"Best quality identification failed: {e}")
            return video_matches[0] if video_matches else None

    async def track_video_availability_changes(
        self, artist: str, title: str
    ) -> Dict[str, Any]:
        """Track changes in video availability across platforms"""
        try:
            # This would be implemented with periodic checks and database storage
            # For now, return current availability status
            current_analysis = await self.correlate_videos_across_platforms(
                artist, title
            )

            availability = {
                "artist": artist,
                "title": title,
                "platforms_available": [
                    p.value
                    for p in Platform
                    if any(
                        p in match.platforms
                        for match in current_analysis.cross_platform_matches
                    )
                ],
                "total_versions": len(current_analysis.cross_platform_matches),
                "last_checked": time.time(),
                "availability_score": len(current_analysis.cross_platform_matches)
                / len(Platform),
            }

            return availability

        except Exception as e:
            logger.error(f"Availability tracking failed: {e}")
            return {}

    async def generate_video_discovery_insights(self, artist: str) -> Dict[str, Any]:
        """Generate insights for video discovery across platforms"""
        try:
            insights = {
                "artist": artist,
                "platform_coverage": {},
                "quality_distribution": {},
                "recommendations": [],
                "generated_at": time.time(),
            }

            # This would analyze historical data to provide insights
            # For now, return basic structure
            for platform in Platform:
                insights["platform_coverage"][platform.value] = {
                    "videos_found": 0,
                    "average_quality": 0.0,
                    "official_content_ratio": 0.0,
                }

            insights["recommendations"] = [
                "Search Vevo for official high-quality content",
                "Check Vimeo for independent artist content",
                "Use YouTube for comprehensive coverage",
                "Cross-reference with IMVDb for metadata",
            ]

            return insights

        except Exception as e:
            logger.error(f"Discovery insights generation failed: {e}")
            return {}

    async def get_intelligence_statistics(self) -> Dict[str, Any]:
        """Get cross-platform video intelligence statistics"""
        try:
            avg_processing_time = self.stats["total_processing_time"] / max(
                1, self.stats["analyses_completed"]
            )

            return {
                "service": "Cross-Platform Video Intelligence",
                "analyses_completed": self.stats["analyses_completed"],
                "cross_platform_matches_found": self.stats[
                    "cross_platform_matches_found"
                ],
                "average_processing_time_seconds": round(avg_processing_time, 2),
                "platform_usage": self.stats["platform_usage"],
                "match_types": self.stats["match_types"],
                "config": self.config,
                "supported_platforms": [p.value for p in Platform],
                "capabilities": {
                    "cross_platform_correlation": True,
                    "quality_analysis": self.config["enable_quality_analysis"],
                    "video_fingerprinting": self.config["enable_fingerprinting"],
                    "best_version_selection": True,
                    "availability_tracking": True,
                },
            }

        except Exception as e:
            logger.error(f"❌ Failed to get intelligence statistics: {e}")
            return {"service": "Cross-Platform Video Intelligence", "error": str(e)}


# Global cross-platform video intelligence service instance
_cross_platform_intelligence_service: Optional[CrossPlatformVideoIntelligence] = None


async def get_cross_platform_video_intelligence(
    config: Optional[Dict[str, Any]] = None
) -> CrossPlatformVideoIntelligence:
    """Get or create global cross-platform video intelligence service instance"""
    global _cross_platform_intelligence_service

    if _cross_platform_intelligence_service is None:
        _cross_platform_intelligence_service = CrossPlatformVideoIntelligence(config)

    return _cross_platform_intelligence_service
