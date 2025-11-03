"""
Duplicate Manager Service - Phase 3 Week 28
Consumer-focused duplicate detection and management for music video collections
"""

import asyncio
import hashlib
import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.music_video_detector import get_music_video_detector
from src.services.redis_service import get_redis_client
from src.services.video_fingerprinting_service import get_video_fingerprinting_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.duplicate_manager")


class DuplicateType(Enum):
    """Types of duplicates detected"""

    EXACT_DUPLICATE = "exact_duplicate"  # Identical files (same hash)
    QUALITY_VARIANT = "quality_variant"  # Same video, different quality
    VERSION_VARIANT = (
        "version_variant"  # Same song, different version (remix, live, etc.)
    )
    SIMILAR_CONTENT = "similar_content"  # Similar but not identical content
    FALSE_POSITIVE = "false_positive"  # Not actually duplicates


class DuplicateConfidence(Enum):
    """Confidence levels for duplicate detection"""

    VERY_HIGH = "very_high"  # 95%+ (exact hash match)
    HIGH = "high"  # 85-94% (very similar fingerprint)
    MEDIUM = "medium"  # 70-84% (similar content)
    LOW = "low"  # 50-69% (possibly similar)
    VERY_LOW = "very_low"  # <50% (unlikely duplicates)


class DuplicateGroup:
    """Group of duplicate/similar videos"""

    def __init__(self, group_id: str):
        self.group_id: str = group_id
        self.duplicate_type: DuplicateType = DuplicateType.SIMILAR_CONTENT
        self.confidence: DuplicateConfidence = DuplicateConfidence.VERY_LOW
        self.master_file: Optional[str] = None  # Highest quality/preferred file
        self.duplicate_files: List[str] = []
        self.similarity_scores: Dict[str, float] = {}
        self.file_metadata: Dict[str, Dict] = {}
        self.detection_factors: Dict[str, Any] = {}
        self.recommendations: List[Dict[str, Any]] = []
        self.created_at: datetime = datetime.now()

    def add_file(
        self,
        file_path: str,
        similarity_score: float = 0.0,
        metadata: Optional[Dict] = None,
    ):
        """Add a file to this duplicate group"""
        if file_path not in self.duplicate_files:
            self.duplicate_files.append(file_path)
            self.similarity_scores[file_path] = similarity_score
            self.file_metadata[file_path] = metadata or {}

    def set_master_file(self, file_path: str):
        """Set the master file (highest quality/preferred)"""
        if file_path in self.duplicate_files:
            self.master_file = file_path

    def get_file_count(self) -> int:
        """Get total number of files in group"""
        return len(self.duplicate_files)

    def get_total_size(self) -> int:
        """Get total size of all files in group"""
        total_size = 0
        for file_path in self.duplicate_files:
            try:
                total_size += os.path.getsize(file_path)
            except:
                pass
        return total_size

    def get_potential_savings(self) -> int:
        """Get potential disk space savings by keeping only master file"""
        total_size = self.get_total_size()
        master_size = 0

        if self.master_file and os.path.exists(self.master_file):
            try:
                master_size = os.path.getsize(self.master_file)
            except:
                pass

        return max(0, total_size - master_size)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "duplicate_type": self.duplicate_type.value,
            "confidence": self.confidence.value,
            "master_file": self.master_file,
            "duplicate_files": self.duplicate_files,
            "similarity_scores": self.similarity_scores,
            "file_metadata": self.file_metadata,
            "detection_factors": self.detection_factors,
            "recommendations": self.recommendations,
            "file_count": self.get_file_count(),
            "total_size": self.get_total_size(),
            "potential_savings": self.get_potential_savings(),
            "created_at": self.created_at.isoformat(),
        }


class DuplicateScanResult:
    """Result of duplicate detection scan"""

    def __init__(self):
        self.total_files_scanned: int = 0
        self.duplicate_groups_found: int = 0
        self.total_duplicates: int = 0
        self.potential_space_savings: int = 0
        self.scan_time_seconds: float = 0.0
        self.groups: List[DuplicateGroup] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_group(self, group: DuplicateGroup):
        """Add a duplicate group to results"""
        self.groups.append(group)
        self.duplicate_groups_found += 1
        self.total_duplicates += group.get_file_count()
        self.potential_space_savings += group.get_potential_savings()

    def get_groups_by_confidence(
        self, min_confidence: DuplicateConfidence
    ) -> List[DuplicateGroup]:
        """Get groups with at least the specified confidence level"""
        confidence_levels = {
            DuplicateConfidence.VERY_HIGH: 5,
            DuplicateConfidence.HIGH: 4,
            DuplicateConfidence.MEDIUM: 3,
            DuplicateConfidence.LOW: 2,
            DuplicateConfidence.VERY_LOW: 1,
        }

        min_level = confidence_levels.get(min_confidence, 1)

        return [
            group
            for group in self.groups
            if confidence_levels.get(group.confidence, 1) >= min_level
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files_scanned": self.total_files_scanned,
            "duplicate_groups_found": self.duplicate_groups_found,
            "total_duplicates": self.total_duplicates,
            "potential_space_savings": self.potential_space_savings,
            "scan_time_seconds": self.scan_time_seconds,
            "groups": [group.to_dict() for group in self.groups],
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": {
                "very_high_confidence": len(
                    self.get_groups_by_confidence(DuplicateConfidence.VERY_HIGH)
                ),
                "high_confidence": len(
                    self.get_groups_by_confidence(DuplicateConfidence.HIGH)
                ),
                "medium_confidence": len(
                    self.get_groups_by_confidence(DuplicateConfidence.MEDIUM)
                ),
                "low_confidence": len(
                    self.get_groups_by_confidence(DuplicateConfidence.LOW)
                ),
            },
        }


class DuplicateManager:
    """Consumer-focused duplicate detection and management system"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.fingerprinting_service = None
        self.music_video_detector = None

        # Similarity thresholds for different confidence levels
        self.similarity_thresholds = {
            DuplicateConfidence.VERY_HIGH: 0.95,
            DuplicateConfidence.HIGH: 0.85,
            DuplicateConfidence.MEDIUM: 0.70,
            DuplicateConfidence.LOW: 0.50,
        }

        # File hash cache for exact duplicate detection
        self.file_hashes: Dict[str, str] = {}

        # Quality scoring factors
        self.quality_factors = {
            "resolution": {"weight": 0.4, "preferences": ["1080p", "720p", "480p"]},
            "bitrate": {"weight": 0.3, "min_good": 1000},
            "codec": {"weight": 0.2, "preferences": ["h264", "h265", "vp9"]},
            "filesize": {"weight": 0.1, "bigger_better": True},
        }

    async def initialize(self):
        """Initialize duplicate manager services"""
        try:
            self.redis_client = await get_redis_client()
            self.fingerprinting_service = await get_video_fingerprinting_service()
            self.music_video_detector = await get_music_video_detector()

            logger.info("Duplicate manager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize duplicate manager: {e}")
            raise

    async def scan_for_duplicates(
        self,
        directory: str,
        scan_subdirs: bool = True,
        min_confidence: DuplicateConfidence = DuplicateConfidence.MEDIUM,
        progress_callback=None,
    ) -> DuplicateScanResult:
        """Scan directory for duplicate music videos"""
        start_time = asyncio.get_event_loop().time()
        result = DuplicateScanResult()

        try:
            # Ensure services are initialized
            if not self.redis_client:
                await self.initialize()

            logger.info(
                f"Starting duplicate scan in {directory} (min_confidence={min_confidence.value})"
            )

            # Find all video files
            video_files = await self._find_video_files(directory, scan_subdirs)
            result.total_files_scanned = len(video_files)

            if len(video_files) < 2:
                result.warnings.append(
                    f"Need at least 2 videos for duplicate detection. Found {len(video_files)}"
                )
                return result

            # Filter to music videos only (optional optimization)
            music_video_files = await self._filter_music_videos(video_files)
            if len(music_video_files) < len(video_files):
                logger.info(
                    f"Filtering to {len(music_video_files)} music videos out of {len(video_files)} total files"
                )
                video_files = music_video_files

            # Calculate file hashes for exact duplicate detection
            logger.info("Calculating file hashes for exact duplicate detection")
            await self._calculate_file_hashes(video_files, progress_callback)

            # Find exact duplicates first
            exact_duplicate_groups = await self._find_exact_duplicates()
            for group in exact_duplicate_groups:
                result.add_group(group)

            # Remove exact duplicates from further processing
            remaining_files = []
            processed_files = set()
            for group in exact_duplicate_groups:
                processed_files.update(group.duplicate_files)

            for file_path in video_files:
                if file_path not in processed_files:
                    remaining_files.append(file_path)

            # Find similar duplicates using fingerprinting
            if len(remaining_files) >= 2:
                logger.info(
                    f"Analyzing {len(remaining_files)} files for similarity duplicates"
                )
                similarity_groups = await self._find_similarity_duplicates(
                    remaining_files, min_confidence, progress_callback
                )

                for group in similarity_groups:
                    result.add_group(group)

            # Generate recommendations for each group
            for group in result.groups:
                await self._generate_group_recommendations(group)

            result.scan_time_seconds = asyncio.get_event_loop().time() - start_time

            logger.info(
                f"Duplicate scan completed: {result.duplicate_groups_found} groups found, "
                f"{result.total_duplicates} total duplicates, "
                f"{result.potential_space_savings / (1024*1024):.1f} MB potential savings"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to scan for duplicates: {e}")
            result.errors.append(f"Scan failed: {e}")
            result.scan_time_seconds = asyncio.get_event_loop().time() - start_time
            return result

    async def remove_duplicates(
        self,
        duplicate_groups: List[DuplicateGroup],
        keep_strategy: str = "highest_quality",
        dry_run: bool = False,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """Remove duplicates based on strategy"""
        removal_result = {
            "files_removed": 0,
            "space_freed": 0,
            "errors": [],
            "warnings": [],
            "removed_files": [],
        }

        try:
            logger.info(
                f"Removing duplicates: {len(duplicate_groups)} groups "
                f"(strategy={keep_strategy}, dry_run={dry_run})"
            )

            for i, group in enumerate(duplicate_groups):
                try:
                    # Determine which file to keep
                    keep_file = await self._determine_file_to_keep(group, keep_strategy)

                    if not keep_file:
                        removal_result["warnings"].append(
                            f"Could not determine file to keep in group {group.group_id}"
                        )
                        continue

                    # Remove other files in group
                    for file_path in group.duplicate_files:
                        if file_path != keep_file:
                            try:
                                if not dry_run:
                                    file_size = os.path.getsize(file_path)
                                    os.remove(file_path)
                                    removal_result["space_freed"] += file_size
                                    logger.info(f"Removed duplicate: {file_path}")
                                else:
                                    file_size = (
                                        os.path.getsize(file_path)
                                        if os.path.exists(file_path)
                                        else 0
                                    )
                                    removal_result["space_freed"] += file_size
                                    logger.info(f"DRY RUN: Would remove {file_path}")

                                removal_result["files_removed"] += 1
                                removal_result["removed_files"].append(file_path)

                            except Exception as e:
                                error_msg = f"Failed to remove {file_path}: {e}"
                                removal_result["errors"].append(error_msg)
                                logger.error(error_msg)

                    if progress_callback:
                        await progress_callback(i + 1, len(duplicate_groups), group)

                except Exception as e:
                    error_msg = (
                        f"Failed to process duplicate group {group.group_id}: {e}"
                    )
                    removal_result["errors"].append(error_msg)
                    logger.error(error_msg)

            logger.info(
                f"Duplicate removal completed: {removal_result['files_removed']} files removed, "
                f"{removal_result['space_freed'] / (1024*1024):.1f} MB freed"
            )

            return removal_result

        except Exception as e:
            logger.error(f"Failed to remove duplicates: {e}")
            removal_result["errors"].append(f"Removal failed: {e}")
            return removal_result

    async def _find_video_files(self, directory: str, scan_subdirs: bool) -> List[str]:
        """Find all video files in directory"""
        video_extensions = {
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        }
        video_files = []

        try:
            directory_path = Path(directory)

            if not directory_path.exists():
                logger.warning(f"Directory does not exist: {directory}")
                return []

            pattern = "**/*" if scan_subdirs else "*"

            for file_path in directory_path.glob(pattern):
                if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                    video_files.append(str(file_path))

            logger.info(f"Found {len(video_files)} video files")

        except Exception as e:
            logger.error(f"Failed to find video files: {e}")

        return sorted(video_files)

    async def _filter_music_videos(self, video_files: List[str]) -> List[str]:
        """Filter list to only include detected music videos"""
        try:
            music_videos = []

            # Use cached detection results if available
            for video_path in video_files:
                cache_key = f"music_video_detection:{hashlib.md5(video_path.encode(), usedforsecurity=False).hexdigest()}"
                cached_result = await self.redis_client.get(cache_key)

                if cached_result:
                    result_data = json.loads(cached_result)
                    if result_data.get("is_music_video", False):
                        music_videos.append(video_path)
                else:
                    # For uncached files, include them (they might be music videos)
                    music_videos.append(video_path)

            return music_videos

        except Exception as e:
            logger.warning(f"Failed to filter music videos, using all files: {e}")
            return video_files

    async def _calculate_file_hashes(
        self, video_files: List[str], progress_callback=None
    ):
        """Calculate file hashes for exact duplicate detection"""
        self.file_hashes = {}

        for i, video_path in enumerate(video_files):
            try:
                # Calculate MD5 hash of file (for duplicate detection, not security)
                hash_md5 = hashlib.md5(usedforsecurity=False)
                with open(video_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        hash_md5.update(chunk)

                self.file_hashes[video_path] = hash_md5.hexdigest()

                if progress_callback and i % 10 == 0:  # Update every 10 files
                    await progress_callback(
                        i, len(video_files), f"Hashing {os.path.basename(video_path)}"
                    )

            except Exception as e:
                logger.warning(f"Failed to calculate hash for {video_path}: {e}")
                self.file_hashes[video_path] = None

    async def _find_exact_duplicates(self) -> List[DuplicateGroup]:
        """Find exact duplicates based on file hashes"""
        groups = []
        hash_to_files = {}

        # Group files by hash
        for file_path, file_hash in self.file_hashes.items():
            if file_hash:  # Skip files where hash calculation failed
                if file_hash not in hash_to_files:
                    hash_to_files[file_hash] = []
                hash_to_files[file_hash].append(file_path)

        # Create duplicate groups for hashes with multiple files
        for file_hash, file_paths in hash_to_files.items():
            if len(file_paths) > 1:
                group = DuplicateGroup(f"exact_{file_hash[:12]}")
                group.duplicate_type = DuplicateType.EXACT_DUPLICATE
                group.confidence = DuplicateConfidence.VERY_HIGH

                # Add all files to group with 100% similarity
                for file_path in file_paths:
                    group.add_file(file_path, 1.0, {"file_hash": file_hash})

                # Set master file (prefer smaller path/name for consistency)
                group.set_master_file(sorted(file_paths)[0])

                group.detection_factors = {
                    "method": "file_hash",
                    "hash": file_hash,
                    "identical_files": len(file_paths),
                }

                groups.append(group)

        logger.info(f"Found {len(groups)} exact duplicate groups")
        return groups

    async def _find_similarity_duplicates(
        self,
        video_files: List[str],
        min_confidence: DuplicateConfidence,
        progress_callback=None,
    ) -> List[DuplicateGroup]:
        """Find similar duplicates using video fingerprinting"""
        groups = []

        try:
            # Generate fingerprints for all files
            fingerprints = {}
            for i, video_path in enumerate(video_files):
                try:
                    # This would use the existing video fingerprinting service
                    fingerprint = (
                        await self.fingerprinting_service.generate_fingerprint(
                            video_path
                        )
                    )
                    fingerprints[video_path] = fingerprint

                    if progress_callback and i % 5 == 0:
                        await progress_callback(
                            i,
                            len(video_files),
                            f"Analyzing {os.path.basename(video_path)}",
                        )

                except Exception as e:
                    logger.warning(
                        f"Failed to generate fingerprint for {video_path}: {e}"
                    )

            # Compare all pairs of fingerprints
            processed_files = set()
            file_paths = list(fingerprints.keys())

            for i, file1 in enumerate(file_paths):
                if file1 in processed_files:
                    continue

                similar_files = [file1]
                similarity_scores = {file1: 1.0}

                for j, file2 in enumerate(file_paths[i + 1 :], i + 1):
                    if file2 in processed_files:
                        continue

                    try:
                        # Calculate similarity between fingerprints
                        similarity = await self._calculate_similarity(
                            fingerprints[file1], fingerprints[file2]
                        )

                        # Check if similarity meets minimum threshold
                        min_threshold = self.similarity_thresholds[min_confidence]
                        if similarity >= min_threshold:
                            similar_files.append(file2)
                            similarity_scores[file2] = similarity
                            processed_files.add(file2)

                    except Exception as e:
                        logger.warning(f"Failed to compare {file1} and {file2}: {e}")

                # Create group if we found similar files
                if len(similar_files) > 1:
                    group_id = f"similar_{hashlib.md5(file1.encode(), usedforsecurity=False).hexdigest()[:12]}"
                    group = DuplicateGroup(group_id)

                    # Determine confidence and type based on average similarity
                    avg_similarity = sum(similarity_scores.values()) / len(
                        similarity_scores
                    )
                    group.confidence = self._similarity_to_confidence(avg_similarity)
                    group.duplicate_type = self._determine_duplicate_type(
                        similar_files, similarity_scores
                    )

                    # Add files to group
                    for file_path in similar_files:
                        group.add_file(file_path, similarity_scores[file_path])

                    # Determine master file (highest quality)
                    master_file = await self._select_highest_quality_file(similar_files)
                    group.set_master_file(master_file)

                    group.detection_factors = {
                        "method": "video_fingerprinting",
                        "average_similarity": avg_similarity,
                        "similarity_range": [
                            min(similarity_scores.values()),
                            max(similarity_scores.values()),
                        ],
                    }

                    groups.append(group)
                    processed_files.add(file1)

            logger.info(f"Found {len(groups)} similarity-based duplicate groups")

        except Exception as e:
            logger.error(f"Failed to find similarity duplicates: {e}")

        return groups

    async def _calculate_similarity(
        self, fingerprint1: Any, fingerprint2: Any
    ) -> float:
        """Calculate similarity between two video fingerprints"""
        try:
            # This would use the existing fingerprinting service's similarity calculation
            similarity = await self.fingerprinting_service.calculate_similarity(
                fingerprint1, fingerprint2
            )
            return similarity
        except Exception as e:
            logger.warning(f"Failed to calculate similarity: {e}")
            return 0.0

    def _similarity_to_confidence(self, similarity: float) -> DuplicateConfidence:
        """Convert similarity score to confidence level"""
        if similarity >= self.similarity_thresholds[DuplicateConfidence.VERY_HIGH]:
            return DuplicateConfidence.VERY_HIGH
        elif similarity >= self.similarity_thresholds[DuplicateConfidence.HIGH]:
            return DuplicateConfidence.HIGH
        elif similarity >= self.similarity_thresholds[DuplicateConfidence.MEDIUM]:
            return DuplicateConfidence.MEDIUM
        elif similarity >= self.similarity_thresholds[DuplicateConfidence.LOW]:
            return DuplicateConfidence.LOW
        else:
            return DuplicateConfidence.VERY_LOW

    def _determine_duplicate_type(
        self, files: List[str], similarity_scores: Dict[str, float]
    ) -> DuplicateType:
        """Determine the type of duplicates based on filenames and similarity"""
        filenames = [os.path.basename(f).lower() for f in files]

        # Check for quality indicators
        quality_keywords = ["720p", "1080p", "4k", "hd", "hq", "low", "high"]
        has_quality_variants = any(
            any(keyword in filename for keyword in quality_keywords)
            for filename in filenames
        )

        if has_quality_variants:
            return DuplicateType.QUALITY_VARIANT

        # Check for version indicators
        version_keywords = [
            "remix",
            "live",
            "acoustic",
            "cover",
            "radio edit",
            "extended",
        ]
        has_version_variants = any(
            any(keyword in filename for keyword in version_keywords)
            for filename in filenames
        )

        if has_version_variants:
            return DuplicateType.VERSION_VARIANT

        # High similarity suggests same content
        avg_similarity = sum(similarity_scores.values()) / len(similarity_scores)
        if avg_similarity >= 0.9:
            return DuplicateType.QUALITY_VARIANT

        return DuplicateType.SIMILAR_CONTENT

    async def _select_highest_quality_file(self, files: List[str]) -> str:
        """Select the highest quality file from a list"""
        try:
            file_scores = {}

            for file_path in files:
                score = await self._calculate_quality_score(file_path)
                file_scores[file_path] = score

            # Return file with highest quality score
            return max(file_scores.items(), key=lambda x: x[1])[0]

        except Exception as e:
            logger.warning(f"Failed to select highest quality file: {e}")
            # Fall back to largest file
            try:
                return max(
                    files, key=lambda x: os.path.getsize(x) if os.path.exists(x) else 0
                )
            except:
                return files[0] if files else None

    async def _calculate_quality_score(self, file_path: str) -> float:
        """Calculate quality score for a file"""
        score = 0.0

        try:
            filename = os.path.basename(file_path).lower()
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

            # Resolution scoring
            if "1080p" in filename or "1080" in filename:
                score += 40
            elif "720p" in filename or "720" in filename:
                score += 30
            elif "480p" in filename or "480" in filename:
                score += 20

            # Quality indicators
            if "hd" in filename or "high" in filename:
                score += 20
            elif "hq" in filename:
                score += 15
            elif "low" in filename:
                score -= 10

            # File size (larger generally better for videos)
            size_mb = file_size / (1024 * 1024)
            if size_mb > 100:
                score += 15
            elif size_mb > 50:
                score += 10
            elif size_mb > 20:
                score += 5

            # Format preferences (would be expanded with actual metadata)
            if ".mp4" in filename:
                score += 10
            elif ".mkv" in filename:
                score += 8
            elif ".avi" in filename:
                score += 5

            return score

        except Exception as e:
            logger.warning(f"Failed to calculate quality score for {file_path}: {e}")
            return 0.0

    async def _determine_file_to_keep(
        self, group: DuplicateGroup, strategy: str
    ) -> Optional[str]:
        """Determine which file to keep based on strategy"""
        if not group.duplicate_files:
            return None

        if strategy == "highest_quality":
            return group.master_file or group.duplicate_files[0]

        elif strategy == "largest_file":
            try:
                return max(
                    group.duplicate_files,
                    key=lambda x: os.path.getsize(x) if os.path.exists(x) else 0,
                )
            except:
                return group.duplicate_files[0]

        elif strategy == "smallest_file":
            try:
                return min(
                    group.duplicate_files,
                    key=lambda x: (
                        os.path.getsize(x) if os.path.exists(x) else float("inf")
                    ),
                )
            except:
                return group.duplicate_files[0]

        elif strategy == "first_alphabetical":
            return sorted(group.duplicate_files)[0]

        else:
            # Default to master file or first file
            return group.master_file or group.duplicate_files[0]

    async def _generate_group_recommendations(self, group: DuplicateGroup):
        """Generate recommendations for handling a duplicate group"""
        recommendations = []

        # Recommend action based on confidence and type
        if group.confidence == DuplicateConfidence.VERY_HIGH:
            if group.duplicate_type == DuplicateType.EXACT_DUPLICATE:
                recommendations.append(
                    {
                        "action": "delete_duplicates",
                        "reason": "Exact duplicates - safe to remove",
                        "keep_file": group.master_file,
                        "confidence": "very_high",
                    }
                )

        elif group.confidence == DuplicateConfidence.HIGH:
            if group.duplicate_type == DuplicateType.QUALITY_VARIANT:
                recommendations.append(
                    {
                        "action": "keep_highest_quality",
                        "reason": "Same content, different quality",
                        "keep_file": group.master_file,
                        "confidence": "high",
                    }
                )
            else:
                recommendations.append(
                    {
                        "action": "manual_review",
                        "reason": "High similarity but unclear relationship",
                        "confidence": "high",
                    }
                )

        else:
            recommendations.append(
                {
                    "action": "manual_review",
                    "reason": f"Medium/low confidence - verify manually",
                    "confidence": group.confidence.value,
                }
            )

        # Add space savings info
        if group.get_potential_savings() > 0:
            savings_mb = group.get_potential_savings() / (1024 * 1024)
            recommendations.append(
                {
                    "action": "space_savings",
                    "reason": f"Could save {savings_mb:.1f} MB by removing duplicates",
                    "savings_bytes": group.get_potential_savings(),
                }
            )

        group.recommendations = recommendations


# Global service instance
_duplicate_manager_instance = None


async def get_duplicate_manager(config: Optional[Dict] = None) -> DuplicateManager:
    """Get global duplicate manager instance"""
    global _duplicate_manager_instance

    if _duplicate_manager_instance is None:
        _duplicate_manager_instance = DuplicateManager(config)
        await _duplicate_manager_instance.initialize()

    return _duplicate_manager_instance
