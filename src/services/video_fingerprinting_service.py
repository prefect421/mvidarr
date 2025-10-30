"""
Video Fingerprinting Service - Phase 3 Week 26
Advanced duplicate detection and video version management for music videos
"""

import asyncio
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.services.media_cache_manager import CacheType, get_media_cache_manager
from src.services.performance_monitor import track_media_processing_time
from src.utils.logger import get_logger

logger = get_logger("mvidarr.video_fingerprinting")


@dataclass
class VideoFingerprint:
    """Video fingerprint data structure"""

    video_id: str
    file_path: str
    file_hash: str
    duration: float
    resolution: str
    bitrate: int
    fps: float
    audio_fingerprint: Optional[str] = None
    visual_hash: Optional[str] = None
    metadata_hash: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "duration": self.duration,
            "resolution": self.resolution,
            "bitrate": self.bitrate,
            "fps": self.fps,
            "audio_fingerprint": self.audio_fingerprint,
            "visual_hash": self.visual_hash,
            "metadata_hash": self.metadata_hash,
            "created_at": self.created_at,
        }


@dataclass
class DuplicateMatch:
    """Duplicate video match result"""

    original_video_id: str
    duplicate_video_id: str
    similarity_score: float
    match_type: str  # 'exact', 'similar', 'remastered', 'different_quality'
    differences: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_video_id": self.original_video_id,
            "duplicate_video_id": self.duplicate_video_id,
            "similarity_score": self.similarity_score,
            "match_type": self.match_type,
            "differences": self.differences,
            "confidence": self.confidence,
        }


class VideoFingerprintingService:
    """Advanced video fingerprinting and duplicate detection service"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize video fingerprinting service"""
        self.config = config or {
            "enable_visual_hashing": True,
            "enable_audio_fingerprinting": True,
            "similarity_threshold": 0.85,
            "exact_match_threshold": 0.98,
            "cache_ttl": 86400,  # 24 hours
            "max_fingerprints_cache": 10000,
        }

        # Storage for video fingerprints
        self.fingerprints: Dict[str, VideoFingerprint] = {}
        self.file_hash_index: Dict[str, str] = {}  # file_hash -> video_id
        self.duration_index: Dict[int, Set[str]] = {}  # duration_bucket -> video_ids

        # Performance tracking
        self.stats = {
            "fingerprints_generated": 0,
            "duplicates_detected": 0,
            "exact_matches": 0,
            "similar_matches": 0,
            "processing_time_total": 0.0,
        }

        logger.info("🔍 Video fingerprinting service initialized")

    async def generate_video_fingerprint(
        self, video_path: str, video_id: Optional[str] = None
    ) -> Optional[VideoFingerprint]:
        """
        Generate comprehensive fingerprint for a video file

        Args:
            video_path: Path to video file
            video_id: Optional video identifier

        Returns:
            VideoFingerprint object with all computed hashes and metadata
        """
        start_time = time.time()

        try:
            video_path_obj = Path(video_path)
            if not video_path_obj.exists():
                logger.error(f"Video file not found: {video_path}")
                return None

            # Generate video ID if not provided
            if not video_id:
                video_id = hashlib.md5(video_path.encode(), usedforsecurity=False).hexdigest()[:16]

            # Check if fingerprint already exists in cache
            cache_manager = await get_media_cache_manager()
            cache_key = f"video_fingerprint_{video_id}"

            cached_fingerprint = await cache_manager.get(
                CacheType.MEDIA_METADATA, cache_key
            )
            if cached_fingerprint:
                return VideoFingerprint(**cached_fingerprint)

            logger.info(f"🔍 Generating fingerprint for video: {video_path_obj.name}")

            # Generate file hash
            file_hash = await self._generate_file_hash(video_path)

            # Extract basic video metadata
            metadata = await self._extract_video_metadata(video_path)
            if not metadata:
                logger.error(f"Failed to extract metadata from: {video_path}")
                return None

            # Create fingerprint object
            fingerprint = VideoFingerprint(
                video_id=video_id,
                file_path=video_path,
                file_hash=file_hash,
                duration=metadata.get("duration", 0.0),
                resolution=metadata.get("resolution", "unknown"),
                bitrate=metadata.get("bitrate", 0),
                fps=metadata.get("fps", 0.0),
                metadata_hash=await self._generate_metadata_hash(metadata),
            )

            # Generate audio fingerprint if enabled
            if self.config["enable_audio_fingerprinting"]:
                fingerprint.audio_fingerprint = await self._generate_audio_fingerprint(
                    video_path
                )

            # Generate visual hash if enabled
            if self.config["enable_visual_hashing"]:
                fingerprint.visual_hash = await self._generate_visual_hash(video_path)

            # Store fingerprint
            self.fingerprints[video_id] = fingerprint
            self.file_hash_index[file_hash] = video_id

            # Add to duration index
            duration_bucket = int(fingerprint.duration // 10) * 10  # 10-second buckets
            if duration_bucket not in self.duration_index:
                self.duration_index[duration_bucket] = set()
            self.duration_index[duration_bucket].add(video_id)

            # Cache fingerprint
            await cache_manager.set(
                CacheType.MEDIA_METADATA,
                cache_key,
                fingerprint.to_dict(),
                ttl=self.config["cache_ttl"],
            )

            # Update statistics
            self.stats["fingerprints_generated"] += 1
            processing_time = time.time() - start_time
            self.stats["processing_time_total"] += processing_time

            # Track performance
            await track_media_processing_time("video_fingerprinting", processing_time)

            logger.info(
                f"✅ Generated fingerprint for {video_path_obj.name} in {processing_time:.2f}s"
            )
            return fingerprint

        except Exception as e:
            logger.error(
                f"❌ Failed to generate video fingerprint for {video_path}: {e}"
            )
            return None

    async def _generate_file_hash(self, video_path: str) -> str:
        """Generate MD5 hash of video file (for fingerprinting, not security)"""
        try:
            hash_md5 = hashlib.md5(usedforsecurity=False)

            # Read file in chunks to handle large videos
            with open(video_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_md5.update(chunk)

            return hash_md5.hexdigest()

        except Exception as e:
            logger.error(f"Failed to generate file hash: {e}")
            return ""

    async def _extract_video_metadata(
        self, video_path: str
    ) -> Optional[Dict[str, Any]]:
        """Extract video metadata using FFprobe"""
        try:
            import json
            import subprocess

            # Use FFprobe to get detailed video information
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                video_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"FFprobe failed: {stderr.decode()}")
                return None

            probe_data = json.loads(stdout.decode())

            # Extract relevant metadata
            video_stream = None
            audio_stream = None

            for stream in probe_data.get("streams", []):
                if stream.get("codec_type") == "video" and not video_stream:
                    video_stream = stream
                elif stream.get("codec_type") == "audio" and not audio_stream:
                    audio_stream = stream

            if not video_stream:
                logger.error("No video stream found")
                return None

            # Build metadata dictionary
            metadata = {
                "duration": float(probe_data.get("format", {}).get("duration", 0)),
                "bitrate": int(probe_data.get("format", {}).get("bit_rate", 0)),
                "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
                "fps": eval(
                    video_stream.get("r_frame_rate", "0/1")
                ),  # Convert fraction to float
                "codec": video_stream.get("codec_name", "unknown"),
                "pixel_format": video_stream.get("pix_fmt", "unknown"),
                "has_audio": audio_stream is not None,
            }

            if audio_stream:
                metadata.update(
                    {
                        "audio_codec": audio_stream.get("codec_name", "unknown"),
                        "sample_rate": int(audio_stream.get("sample_rate", 0)),
                        "channels": int(audio_stream.get("channels", 0)),
                    }
                )

            return metadata

        except Exception as e:
            logger.error(f"Failed to extract video metadata: {e}")
            return None

    async def _generate_metadata_hash(self, metadata: Dict[str, Any]) -> str:
        """Generate hash of video metadata for comparison"""
        try:
            # Create normalized metadata string
            normalized = {
                "duration": round(metadata.get("duration", 0), 1),
                "resolution": metadata.get("resolution", ""),
                "fps": round(metadata.get("fps", 0), 1),
                "codec": metadata.get("codec", ""),
                "has_audio": metadata.get("has_audio", False),
            }

            metadata_str = json.dumps(normalized, sort_keys=True)
            return hashlib.md5(metadata_str.encode(), usedforsecurity=False).hexdigest()

        except Exception as e:
            logger.error(f"Failed to generate metadata hash: {e}")
            return ""

    async def _generate_audio_fingerprint(self, video_path: str) -> Optional[str]:
        """Generate audio fingerprint for duplicate detection"""
        try:
            # Extract audio sample using FFmpeg
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_audio_path = temp_audio.name

            try:
                # Extract 30-second audio sample from middle of video
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    video_path,
                    "-ss",
                    "30",  # Start 30 seconds in
                    "-t",
                    "30",  # Extract 30 seconds
                    "-vn",  # No video
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "22050",  # Sample rate
                    "-ac",
                    "1",  # Mono
                    temp_audio_path,
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )

                await process.communicate()

                if process.returncode != 0:
                    return None

                # Generate hash of audio data
                with open(temp_audio_path, "rb") as f:
                    audio_data = f.read()
                    return hashlib.md5(audio_data, usedforsecurity=False).hexdigest()

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_audio_path)
                except:
                    pass

        except Exception as e:
            logger.debug(f"Audio fingerprinting failed: {e}")
            return None

    async def _generate_visual_hash(self, video_path: str) -> Optional[str]:
        """Generate visual hash from video frames"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_frame:
                temp_frame_path = temp_frame.name

            try:
                # Extract representative frame from middle of video
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    video_path,
                    "-ss",
                    "30",  # 30 seconds in
                    "-vframes",
                    "1",
                    "-vf",
                    "scale=64:64",  # Small scale for hashing
                    temp_frame_path,
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )

                await process.communicate()

                if process.returncode != 0:
                    return None

                # Generate hash of frame data
                with open(temp_frame_path, "rb") as f:
                    frame_data = f.read()
                    return hashlib.md5(frame_data, usedforsecurity=False).hexdigest()

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_frame_path)
                except:
                    pass

        except Exception as e:
            logger.debug(f"Visual hashing failed: {e}")
            return None

    async def detect_duplicate_versions(
        self, video_fingerprint: VideoFingerprint
    ) -> List[DuplicateMatch]:
        """
        Detect duplicate versions of a video

        Args:
            video_fingerprint: Fingerprint of video to check for duplicates

        Returns:
            List of duplicate matches found
        """
        start_time = time.time()
        matches = []

        try:
            logger.info(
                f"🔍 Checking for duplicates of video: {video_fingerprint.video_id}"
            )

            # Check for exact file hash matches first
            if video_fingerprint.file_hash in self.file_hash_index:
                existing_id = self.file_hash_index[video_fingerprint.file_hash]
                if existing_id != video_fingerprint.video_id:
                    matches.append(
                        DuplicateMatch(
                            original_video_id=existing_id,
                            duplicate_video_id=video_fingerprint.video_id,
                            similarity_score=1.0,
                            match_type="exact",
                            confidence=1.0,
                        )
                    )
                    self.stats["exact_matches"] += 1

            # Check similar videos by duration
            duration_bucket = int(video_fingerprint.duration // 10) * 10
            similar_duration_videos = set()

            # Check adjacent duration buckets for similar videos
            for bucket in [duration_bucket - 10, duration_bucket, duration_bucket + 10]:
                similar_duration_videos.update(self.duration_index.get(bucket, set()))

            # Remove self from comparison
            similar_duration_videos.discard(video_fingerprint.video_id)

            # Compare with similar duration videos
            for candidate_id in similar_duration_videos:
                if candidate_id not in self.fingerprints:
                    continue

                candidate_fp = self.fingerprints[candidate_id]
                match = await self._compare_fingerprints(
                    video_fingerprint, candidate_fp
                )

                if (
                    match
                    and match.similarity_score >= self.config["similarity_threshold"]
                ):
                    matches.append(match)
                    self.stats["similar_matches"] += 1

            # Update statistics
            self.stats["duplicates_detected"] += len(matches)
            processing_time = time.time() - start_time

            # Track performance
            await track_media_processing_time("duplicate_detection", processing_time)

            logger.info(
                f"🔍 Found {len(matches)} potential duplicates in {processing_time:.2f}s"
            )
            return matches

        except Exception as e:
            logger.error(f"❌ Duplicate detection failed: {e}")
            return []

    async def _compare_fingerprints(
        self, fp1: VideoFingerprint, fp2: VideoFingerprint
    ) -> Optional[DuplicateMatch]:
        """Compare two video fingerprints for similarity"""
        try:
            # Calculate various similarity scores
            similarities = {}
            differences = []

            # Duration similarity
            duration_diff = abs(fp1.duration - fp2.duration)
            duration_similarity = max(
                0, 1 - (duration_diff / max(fp1.duration, fp2.duration))
            )
            similarities["duration"] = duration_similarity

            if duration_diff > 5:  # More than 5 seconds difference
                differences.append(f"Duration difference: {duration_diff:.1f}s")

            # Resolution similarity
            if fp1.resolution == fp2.resolution:
                similarities["resolution"] = 1.0
            else:
                similarities["resolution"] = 0.5
                differences.append(
                    f"Resolution difference: {fp1.resolution} vs {fp2.resolution}"
                )

            # Audio fingerprint similarity
            if fp1.audio_fingerprint and fp2.audio_fingerprint:
                if fp1.audio_fingerprint == fp2.audio_fingerprint:
                    similarities["audio"] = 1.0
                else:
                    similarities["audio"] = 0.0
                    differences.append("Audio fingerprint mismatch")

            # Visual hash similarity
            if fp1.visual_hash and fp2.visual_hash:
                if fp1.visual_hash == fp2.visual_hash:
                    similarities["visual"] = 1.0
                else:
                    similarities["visual"] = 0.0
                    differences.append("Visual hash mismatch")

            # Metadata similarity
            if fp1.metadata_hash == fp2.metadata_hash:
                similarities["metadata"] = 1.0
            else:
                similarities["metadata"] = 0.5
                differences.append("Metadata differences")

            # Calculate overall similarity score
            weights = {
                "duration": 0.3,
                "resolution": 0.2,
                "audio": 0.3,
                "visual": 0.1,
                "metadata": 0.1,
            }

            overall_similarity = 0.0
            total_weight = 0.0

            for metric, score in similarities.items():
                weight = weights.get(metric, 0.1)
                overall_similarity += score * weight
                total_weight += weight

            if total_weight > 0:
                overall_similarity /= total_weight

            # Determine match type
            if overall_similarity >= self.config["exact_match_threshold"]:
                match_type = "exact"
            elif overall_similarity >= 0.9:
                match_type = "similar"
            elif overall_similarity >= 0.7:
                match_type = "remastered"
            else:
                match_type = "different_quality"

            # Calculate confidence
            confidence = min(1.0, overall_similarity * 1.2)

            return DuplicateMatch(
                original_video_id=fp2.video_id,  # Existing video is "original"
                duplicate_video_id=fp1.video_id,
                similarity_score=overall_similarity,
                match_type=match_type,
                differences=differences,
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"Failed to compare fingerprints: {e}")
            return None

    async def identify_remastered_versions(
        self, artist: str, title: str
    ) -> List[Dict[str, Any]]:
        """Identify different versions/remasters of the same music video"""
        try:
            # Find all videos matching artist and title
            matching_videos = []

            for video_id, fingerprint in self.fingerprints.items():
                # This would need integration with video metadata to match by artist/title
                # For now, this is a placeholder for the logic
                matching_videos.append(fingerprint)

            # Group by similarity
            version_groups = await self._group_video_versions(matching_videos)

            return version_groups

        except Exception as e:
            logger.error(f"❌ Failed to identify remastered versions: {e}")
            return []

    async def _group_video_versions(
        self, videos: List[VideoFingerprint]
    ) -> List[Dict[str, Any]]:
        """Group videos by version/quality"""
        try:
            groups = []

            # Simple grouping by resolution and duration similarity
            resolution_groups = {}

            for video in videos:
                resolution = video.resolution
                if resolution not in resolution_groups:
                    resolution_groups[resolution] = []
                resolution_groups[resolution].append(video)

            # Convert to result format
            for resolution, video_list in resolution_groups.items():
                if len(video_list) > 1:
                    groups.append(
                        {
                            "resolution": resolution,
                            "video_count": len(video_list),
                            "videos": [v.to_dict() for v in video_list],
                            "type": "resolution_variants",
                        }
                    )

            return groups

        except Exception as e:
            logger.error(f"Failed to group video versions: {e}")
            return []

    async def get_fingerprinting_statistics(self) -> Dict[str, Any]:
        """Get video fingerprinting service statistics"""
        try:
            cache_manager = await get_media_cache_manager()
            cache_stats = await cache_manager.get_statistics()

            return {
                "service": "Video Fingerprinting",
                "fingerprints_stored": len(self.fingerprints),
                "file_hash_index_size": len(self.file_hash_index),
                "duration_buckets": len(self.duration_index),
                "performance_stats": self.stats,
                "cache_stats": cache_stats,
                "config": self.config,
                "capabilities": {
                    "file_hashing": True,
                    "audio_fingerprinting": self.config["enable_audio_fingerprinting"],
                    "visual_hashing": self.config["enable_visual_hashing"],
                    "duplicate_detection": True,
                    "version_identification": True,
                },
            }

        except Exception as e:
            logger.error(f"❌ Failed to get fingerprinting statistics: {e}")
            return {"service": "Video Fingerprinting", "error": str(e)}


# Global video fingerprinting service instance
_video_fingerprinting_service: Optional[VideoFingerprintingService] = None


async def get_video_fingerprinting_service(
    config: Optional[Dict[str, Any]] = None
) -> VideoFingerprintingService:
    """Get or create global video fingerprinting service instance"""
    global _video_fingerprinting_service

    if _video_fingerprinting_service is None:
        _video_fingerprinting_service = VideoFingerprintingService(config)

    return _video_fingerprinting_service
