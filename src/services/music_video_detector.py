"""
Music Video Detection Service - Phase 3 Week 28
Consumer-focused music video identification and classification
"""

import asyncio
import hashlib
import json
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.enhanced_artist_discovery_service import get_enhanced_artist_discovery
from src.services.genre_service import get_genre_service
from src.services.music_video_quality_service import get_music_video_quality_service
from src.services.redis_service import get_redis_client
from src.services.video_fingerprinting_service import get_video_fingerprinting_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.music_video_detector")


class MusicVideoType(Enum):
    """Types of music videos for consumer classification"""

    OFFICIAL_MUSIC_VIDEO = "official_music_video"
    LIVE_PERFORMANCE = "live_performance"
    LYRIC_VIDEO = "lyric_video"
    ACOUSTIC_VERSION = "acoustic_version"
    REMIX_VERSION = "remix_version"
    COVER_VERSION = "cover_version"
    MUSIC_DOCUMENTARY = "music_documentary"
    CONCERT_FOOTAGE = "concert_footage"
    UNKNOWN = "unknown"


class DetectionConfidence(Enum):
    """Confidence levels for music video detection"""

    VERY_HIGH = "very_high"  # 90%+
    HIGH = "high"  # 75-89%
    MEDIUM = "medium"  # 50-74%
    LOW = "low"  # 25-49%
    VERY_LOW = "very_low"  # <25%


class MusicVideoDetectionResult:
    """Result of music video detection analysis"""

    def __init__(self):
        self.is_music_video: bool = False
        self.confidence: DetectionConfidence = DetectionConfidence.VERY_LOW
        self.video_type: MusicVideoType = MusicVideoType.UNKNOWN
        self.detected_artist: Optional[str] = None
        self.detected_title: Optional[str] = None
        self.detected_genres: List[str] = []
        self.detection_factors: Dict[str, Any] = {}
        self.quality_assessment: Optional[Dict] = None
        self.suggested_organization: Optional[Dict] = None
        self.processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_music_video": self.is_music_video,
            "confidence": self.confidence.value,
            "video_type": self.video_type.value,
            "detected_artist": self.detected_artist,
            "detected_title": self.detected_title,
            "detected_genres": self.detected_genres,
            "detection_factors": self.detection_factors,
            "quality_assessment": self.quality_assessment,
            "suggested_organization": self.suggested_organization,
            "processing_time_ms": self.processing_time_ms,
        }


class MusicVideoDetector:
    """Consumer-focused music video detection and classification service"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.artist_discovery = None
        self.genre_service = None
        self.quality_service = None
        self.fingerprinting_service = None

        # Consumer-focused detection patterns
        self.music_keywords = {
            "official_video": [
                "official",
                "music video",
                "mv",
                "videoclip",
                "video clip",
            ],
            "live_performance": [
                "live",
                "concert",
                "performance",
                "tour",
                "festival",
                "acoustic",
            ],
            "lyric_video": ["lyrics", "lyric video", "with lyrics", "letra", "paroles"],
            "remix": ["remix", "mix", "edit", "version", "bootleg", "mashup"],
            "cover": ["cover", "covers", "tribute", "karaoke", "instrumental"],
        }

        # File naming patterns for music videos
        self.filename_patterns = {
            "artist_title": re.compile(
                r"^([^-]+)\s*-\s*(.+?)(?:\s*\([^)]*\))?(?:\.[^.]+)?$"
            ),
            "title_artist": re.compile(
                r"^(.+?)\s*-\s*([^-]+)(?:\s*\([^)]*\))?(?:\.[^.]+)?$"
            ),
            "artist_album_title": re.compile(
                r"^([^-]+)\s*-\s*([^-]+)\s*-\s*(.+?)(?:\.[^.]+)?$"
            ),
        }

        # Audio/video indicators for music content
        self.music_indicators = {
            "audio_codec": ["aac", "mp3", "flac", "ogg", "wav"],
            "video_aspects": [
                "16:9",
                "4:3",
                "21:9",
            ],  # Common music video aspect ratios
            "duration_range": (60, 600),  # 1-10 minutes typical for music videos
            "bitrate_range": (128, 320),  # Audio bitrate range
        }

    async def initialize(self):
        """Initialize detector services"""
        try:
            self.redis_client = await get_redis_client()
            self.artist_discovery = await get_enhanced_artist_discovery()
            self.genre_service = await get_genre_service()
            self.quality_service = await get_music_video_quality_service()
            self.fingerprinting_service = await get_video_fingerprinting_service()

            logger.info("Music video detector initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize music video detector: {e}")
            raise

    async def detect_music_video(
        self, video_path: str, metadata: Optional[Dict] = None
    ) -> MusicVideoDetectionResult:
        """
        Detect if a video is a music video and classify it
        Consumer-focused with practical detection methods
        """
        start_time = asyncio.get_event_loop().time()
        result = MusicVideoDetectionResult()

        try:
            # Ensure services are initialized
            if not self.redis_client:
                await self.initialize()

            # Check cache first
            cache_key = f"music_video_detection:{hashlib.md5(video_path.encode(), usedforsecurity=False).hexdigest()}"
            cached_result = await self.redis_client.get(cache_key)
            if cached_result:
                logger.debug(f"Using cached detection result for {video_path}")
                return MusicVideoDetectionResult(**json.loads(cached_result))

            # Gather detection evidence
            evidence = await self._gather_detection_evidence(video_path, metadata)

            # Analyze evidence to determine if it's a music video
            result = await self._analyze_music_video_evidence(evidence, video_path)

            # Add quality assessment if it's a music video
            if (
                result.is_music_video
                and result.confidence != DetectionConfidence.VERY_LOW
            ):
                result.quality_assessment = await self._assess_music_video_quality(
                    video_path
                )
                result.suggested_organization = await self._suggest_organization(result)

            # Calculate processing time
            result.processing_time_ms = (
                asyncio.get_event_loop().time() - start_time
            ) * 1000

            # Cache result for 1 hour
            await self.redis_client.setex(cache_key, 3600, json.dumps(result.to_dict()))

            logger.info(
                f"Music video detection completed for {os.path.basename(video_path)}: "
                f"{'Music Video' if result.is_music_video else 'Not Music Video'} "
                f"({result.confidence.value})"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to detect music video for {video_path}: {e}")
            result.processing_time_ms = (
                asyncio.get_event_loop().time() - start_time
            ) * 1000
            return result

    async def _gather_detection_evidence(
        self, video_path: str, metadata: Optional[Dict]
    ) -> Dict[str, Any]:
        """Gather all available evidence for music video detection"""
        evidence = {
            "filename": os.path.basename(video_path),
            "filepath": video_path,
            "directory_structure": self._analyze_directory_structure(video_path),
            "filename_analysis": self._analyze_filename(os.path.basename(video_path)),
            "metadata": metadata or {},
            "file_size": (
                os.path.getsize(video_path) if os.path.exists(video_path) else 0
            ),
            "technical_metadata": await self._get_technical_metadata(video_path),
            "existing_artist_match": None,
            "genre_indicators": [],
        }

        # Try to match against existing artists
        if evidence["filename_analysis"]["artist"]:
            evidence["existing_artist_match"] = await self._find_matching_artist(
                evidence["filename_analysis"]["artist"]
            )

        # Look for genre indicators
        evidence["genre_indicators"] = await self._detect_genre_indicators(evidence)

        return evidence

    def _analyze_directory_structure(self, video_path: str) -> Dict[str, Any]:
        """Analyze directory structure for music video indicators"""
        path = Path(video_path)
        structure_info = {
            "is_in_music_directory": False,
            "artist_directory": None,
            "album_directory": None,
            "year_indicator": None,
            "music_keywords": [],
        }

        # Check path components for music-related keywords
        path_parts = [part.lower() for part in path.parts]

        music_dir_keywords = ["music", "videos", "musicvideos", "mv", "clips"]
        for keyword in music_dir_keywords:
            if any(keyword in part for part in path_parts):
                structure_info["is_in_music_directory"] = True
                structure_info["music_keywords"].append(keyword)

        # Try to identify artist directory (usually parent or grandparent)
        if len(path.parts) >= 2:
            potential_artist = path.parent.name
            if not any(char.isdigit() for char in potential_artist[:4]):  # Not a year
                structure_info["artist_directory"] = potential_artist

        # Look for year indicators
        year_pattern = re.compile(r"(19|20)\d{2}")
        for part in path.parts:
            year_match = year_pattern.search(part)
            if year_match:
                structure_info["year_indicator"] = int(year_match.group())
                break

        return structure_info

    def _analyze_filename(self, filename: str) -> Dict[str, Any]:
        """Analyze filename for artist, title, and type indicators"""
        filename_lower = filename.lower()
        base_name = os.path.splitext(filename)[0]

        analysis = {
            "artist": None,
            "title": None,
            "video_type_indicators": [],
            "quality_indicators": [],
            "year": None,
            "parsing_confidence": 0.0,
        }

        # Check for video type keywords
        for video_type, keywords in self.music_keywords.items():
            for keyword in keywords:
                if keyword in filename_lower:
                    analysis["video_type_indicators"].append(
                        {
                            "type": video_type,
                            "keyword": keyword,
                            "position": filename_lower.find(keyword),
                        }
                    )

        # Check for quality indicators
        quality_keywords = [
            "hd",
            "720p",
            "1080p",
            "4k",
            "hq",
            "high quality",
            "official",
        ]
        for keyword in quality_keywords:
            if keyword in filename_lower:
                analysis["quality_indicators"].append(keyword)

        # Try to parse artist and title from filename
        for pattern_name, pattern in self.filename_patterns.items():
            match = pattern.match(base_name)
            if match:
                if pattern_name == "artist_title":
                    analysis["artist"] = match.group(1).strip()
                    analysis["title"] = match.group(2).strip()
                    analysis["parsing_confidence"] = 0.8
                elif pattern_name == "title_artist":
                    analysis["title"] = match.group(1).strip()
                    analysis["artist"] = match.group(2).strip()
                    analysis["parsing_confidence"] = 0.6
                elif pattern_name == "artist_album_title":
                    analysis["artist"] = match.group(1).strip()
                    analysis["title"] = match.group(3).strip()
                    analysis["parsing_confidence"] = 0.7
                break

        # Look for year in filename
        year_pattern = re.compile(r"\b(19|20)\d{2}\b")
        year_match = year_pattern.search(filename)
        if year_match:
            analysis["year"] = int(year_match.group())

        return analysis

    async def _get_technical_metadata(self, video_path: str) -> Dict[str, Any]:
        """Get technical metadata relevant to music video detection"""
        try:
            # This would integrate with existing FFmpeg metadata extraction
            # For now, return placeholder that would be populated by actual FFprobe
            technical_info = {
                "duration_seconds": 0,
                "video_codec": None,
                "audio_codec": None,
                "resolution": None,
                "aspect_ratio": None,
                "bitrate": 0,
                "has_audio": False,
                "audio_channels": 0,
                "frame_rate": 0,
            }

            # In production, this would call existing FFmpeg services
            # technical_info = await self.ffmpeg_service.extract_metadata(video_path)

            return technical_info

        except Exception as e:
            logger.warning(
                f"Could not extract technical metadata for {video_path}: {e}"
            )
            return {}

    async def _find_matching_artist(self, artist_name: str) -> Optional[Dict]:
        """Find matching artist in existing database"""
        try:
            if not self.artist_discovery:
                return None

            # Use existing artist discovery service to find matches
            matches = await self.artist_discovery.search_artists(artist_name, limit=1)
            if matches:
                return {
                    "artist_id": matches[0].id,
                    "name": matches[0].name,
                    "confidence": 0.8,  # Would be calculated based on string similarity
                }

        except Exception as e:
            logger.warning(f"Could not find matching artist for {artist_name}: {e}")

        return None

    async def _detect_genre_indicators(self, evidence: Dict[str, Any]) -> List[str]:
        """Detect genre indicators from various evidence sources"""
        genre_indicators = []

        # Genre keywords that might appear in filenames or paths
        genre_keywords = {
            "rock": ["rock", "metal", "punk", "grunge", "alternative"],
            "pop": ["pop", "dance", "electronic", "edm"],
            "hip_hop": ["hip hop", "rap", "hiphop", "hip-hop"],
            "country": ["country", "folk", "bluegrass"],
            "jazz": ["jazz", "blues", "swing"],
            "classical": ["classical", "orchestra", "symphony"],
        }

        filename_lower = evidence["filename"].lower()
        filepath_lower = evidence["filepath"].lower()

        for genre, keywords in genre_keywords.items():
            for keyword in keywords:
                if keyword in filename_lower or keyword in filepath_lower:
                    genre_indicators.append(genre)
                    break

        return genre_indicators

    async def _analyze_music_video_evidence(
        self, evidence: Dict[str, Any], video_path: str
    ) -> MusicVideoDetectionResult:
        """Analyze all evidence to determine if video is a music video"""
        result = MusicVideoDetectionResult()
        confidence_score = 0.0
        detection_factors = {}

        # Factor 1: Directory structure (20% weight)
        dir_score = 0.0
        if evidence["directory_structure"]["is_in_music_directory"]:
            dir_score += 0.8
        if evidence["directory_structure"]["artist_directory"]:
            dir_score += 0.6
        if evidence["directory_structure"]["music_keywords"]:
            dir_score += 0.4

        dir_score = min(dir_score, 1.0)
        confidence_score += dir_score * 0.2
        detection_factors["directory_structure"] = dir_score

        # Factor 2: Filename analysis (30% weight)
        filename_score = 0.0
        filename_analysis = evidence["filename_analysis"]

        if filename_analysis["artist"] and filename_analysis["title"]:
            filename_score += 0.7
        if filename_analysis["video_type_indicators"]:
            filename_score += 0.5
        if filename_analysis["quality_indicators"]:
            filename_score += 0.3
        if filename_analysis["parsing_confidence"] > 0.5:
            filename_score += filename_analysis["parsing_confidence"] * 0.4

        filename_score = min(filename_score, 1.0)
        confidence_score += filename_score * 0.3
        detection_factors["filename_analysis"] = filename_score

        # Factor 3: Existing artist match (25% weight)
        artist_match_score = 0.0
        if evidence["existing_artist_match"]:
            artist_match_score = evidence["existing_artist_match"]["confidence"]
            result.detected_artist = evidence["existing_artist_match"]["name"]

        confidence_score += artist_match_score * 0.25
        detection_factors["artist_match"] = artist_match_score

        # Factor 4: Technical metadata (15% weight)
        technical_score = 0.0
        tech_meta = evidence["technical_metadata"]

        if tech_meta.get("has_audio"):
            technical_score += 0.6

        duration = tech_meta.get("duration_seconds", 0)
        if (
            self.music_indicators["duration_range"][0]
            <= duration
            <= self.music_indicators["duration_range"][1]
        ):
            technical_score += 0.4

        technical_score = min(technical_score, 1.0)
        confidence_score += technical_score * 0.15
        detection_factors["technical_metadata"] = technical_score

        # Factor 5: Genre indicators (10% weight)
        genre_score = 0.0
        if evidence["genre_indicators"]:
            genre_score = min(len(evidence["genre_indicators"]) * 0.3, 1.0)
            result.detected_genres = evidence["genre_indicators"]

        confidence_score += genre_score * 0.1
        detection_factors["genre_indicators"] = genre_score

        # Determine final result
        result.detection_factors = detection_factors

        if confidence_score >= 0.9:
            result.confidence = DetectionConfidence.VERY_HIGH
        elif confidence_score >= 0.75:
            result.confidence = DetectionConfidence.HIGH
        elif confidence_score >= 0.5:
            result.confidence = DetectionConfidence.MEDIUM
        elif confidence_score >= 0.25:
            result.confidence = DetectionConfidence.LOW
        else:
            result.confidence = DetectionConfidence.VERY_LOW

        # Consider it a music video if confidence is MEDIUM or higher
        result.is_music_video = result.confidence in [
            DetectionConfidence.MEDIUM,
            DetectionConfidence.HIGH,
            DetectionConfidence.VERY_HIGH,
        ]

        # Determine video type
        result.video_type = await self._determine_video_type(
            evidence, result.confidence
        )

        # Set detected title if available
        if filename_analysis["title"]:
            result.detected_title = filename_analysis["title"]

        return result

    async def _determine_video_type(
        self, evidence: Dict[str, Any], confidence: DetectionConfidence
    ) -> MusicVideoType:
        """Determine the specific type of music video"""
        filename_analysis = evidence["filename_analysis"]

        # Check for specific video type indicators
        type_scores = {}

        for indicator in filename_analysis["video_type_indicators"]:
            video_type = indicator["type"]
            if video_type not in type_scores:
                type_scores[video_type] = 0
            type_scores[video_type] += 1

        # Return the type with highest score, or OFFICIAL_MUSIC_VIDEO as default
        if type_scores:
            best_type = max(type_scores.items(), key=lambda x: x[1])[0]

            type_mapping = {
                "official_video": MusicVideoType.OFFICIAL_MUSIC_VIDEO,
                "live_performance": MusicVideoType.LIVE_PERFORMANCE,
                "lyric_video": MusicVideoType.LYRIC_VIDEO,
                "remix": MusicVideoType.REMIX_VERSION,
                "cover": MusicVideoType.COVER_VERSION,
            }

            return type_mapping.get(best_type, MusicVideoType.OFFICIAL_MUSIC_VIDEO)

        # Default to official music video for high confidence detections
        if confidence in [DetectionConfidence.HIGH, DetectionConfidence.VERY_HIGH]:
            return MusicVideoType.OFFICIAL_MUSIC_VIDEO

        return MusicVideoType.UNKNOWN

    async def _assess_music_video_quality(self, video_path: str) -> Optional[Dict]:
        """Assess music video quality using existing quality service"""
        try:
            if not self.quality_service:
                return None

            # Use existing music video quality service
            quality_result = await self.quality_service.analyze_video_quality(
                video_path
            )
            return quality_result.to_dict() if quality_result else None

        except Exception as e:
            logger.warning(f"Could not assess video quality for {video_path}: {e}")
            return None

    async def _suggest_organization(
        self, result: MusicVideoDetectionResult
    ) -> Optional[Dict]:
        """Suggest how to organize this music video in the collection"""
        if not result.is_music_video:
            return None

        organization = {
            "suggested_path": None,
            "artist_folder": None,
            "filename_format": None,
            "metadata_suggestions": {},
        }

        # Suggest artist folder organization
        if result.detected_artist:
            # Clean artist name for folder
            clean_artist = re.sub(r'[<>:"/\\|?*]', "", result.detected_artist)
            organization["artist_folder"] = clean_artist

            # Suggest filename format
            if result.detected_title:
                clean_title = re.sub(r'[<>:"/\\|?*]', "", result.detected_title)
                organization["filename_format"] = f"{clean_artist} - {clean_title}"

                # Suggest full path
                organization[
                    "suggested_path"
                ] = f"Music Videos/{clean_artist}/{clean_artist} - {clean_title}"

        # Metadata suggestions
        organization["metadata_suggestions"] = {
            "video_type": result.video_type.value,
            "confidence": result.confidence.value,
            "detected_genres": result.detected_genres,
            "quality_score": (
                result.quality_assessment.get("overall_score")
                if result.quality_assessment
                else None
            ),
        }

        return organization

    async def batch_detect_music_videos(
        self, video_paths: List[str], progress_callback=None
    ) -> List[MusicVideoDetectionResult]:
        """Batch process multiple videos for music video detection"""
        results = []
        total_videos = len(video_paths)

        logger.info(f"Starting batch music video detection for {total_videos} videos")

        for i, video_path in enumerate(video_paths):
            try:
                result = await self.detect_music_video(video_path)
                results.append(result)

                if progress_callback:
                    await progress_callback(i + 1, total_videos, video_path, result)

            except Exception as e:
                logger.error(f"Failed to detect music video for {video_path}: {e}")
                # Add failed result
                failed_result = MusicVideoDetectionResult()
                failed_result.detection_factors["error"] = str(e)
                results.append(failed_result)

        logger.info(
            f"Batch music video detection completed. "
            f"{sum(1 for r in results if r.is_music_video)} music videos detected "
            f"out of {total_videos} files"
        )

        return results

    async def get_detection_statistics(self) -> Dict[str, Any]:
        """Get statistics about music video detection performance"""
        try:
            # This would query detection cache/database for statistics
            stats = {
                "total_detections": 0,
                "music_videos_found": 0,
                "confidence_distribution": {
                    "very_high": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "very_low": 0,
                },
                "video_types": {
                    "official_music_video": 0,
                    "live_performance": 0,
                    "lyric_video": 0,
                    "acoustic_version": 0,
                    "remix_version": 0,
                    "cover_version": 0,
                    "unknown": 0,
                },
                "avg_processing_time_ms": 0.0,
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to get detection statistics: {e}")
            return {}


# Global service instance
_music_video_detector_instance = None


async def get_music_video_detector(config: Optional[Dict] = None) -> MusicVideoDetector:
    """Get global music video detector instance"""
    global _music_video_detector_instance

    if _music_video_detector_instance is None:
        _music_video_detector_instance = MusicVideoDetector(config)
        await _music_video_detector_instance.initialize()

    return _music_video_detector_instance
