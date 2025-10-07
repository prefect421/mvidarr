"""
Collection Maintenance Service - Phase 4 Week 31
Collection maintenance and cleanup tools for personal music video collections
"""

import asyncio
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import aiofiles
from sqlalchemy import and_, asc, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database.async_connection import get_async_session
from src.database.models import Artist, Video
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.collection_maintenance")


class MaintenanceType(Enum):
    """Types of maintenance operations"""

    DUPLICATE_DETECTION = "duplicate_detection"
    BROKEN_LINK_CLEANUP = "broken_link_cleanup"
    ORPHANED_FILES = "orphaned_files"
    METADATA_CLEANUP = "metadata_cleanup"
    THUMBNAIL_REGENERATION = "thumbnail_regeneration"
    STORAGE_OPTIMIZATION = "storage_optimization"
    DATABASE_CLEANUP = "database_cleanup"
    CACHE_CLEANUP = "cache_cleanup"


class MaintenanceStatus(Enum):
    """Maintenance task status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DuplicateStrategy(Enum):
    """Duplicate handling strategies"""

    KEEP_HIGHEST_QUALITY = "keep_highest_quality"
    KEEP_NEWEST = "keep_newest"
    KEEP_LARGEST_FILE = "keep_largest_file"
    KEEP_MOST_WATCHED = "keep_most_watched"
    MANUAL_REVIEW = "manual_review"


@dataclass
class DuplicateGroup:
    """Group of duplicate videos"""

    group_id: str
    title_similarity: float
    videos: List[Dict[str, Any]]
    recommended_keeper: int
    total_size_bytes: int
    potential_savings_bytes: int
    duplicate_reason: str


@dataclass
class MaintenanceTask:
    """Maintenance task definition"""

    task_id: str
    task_type: MaintenanceType
    status: MaintenanceStatus
    progress_percent: float
    items_processed: int
    total_items: int
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    results: Dict[str, Any]


@dataclass
class StorageAnalysis:
    """Storage usage analysis"""

    total_size_gb: float
    video_files_size_gb: float
    thumbnail_size_gb: float
    cache_size_gb: float
    temp_files_size_gb: float
    orphaned_files_size_gb: float
    largest_files: List[Dict[str, Any]]
    oldest_files: List[Dict[str, Any]]
    duplicate_waste_gb: float


@dataclass
class CleanupResult:
    """Cleanup operation result"""

    operation: str
    items_found: int
    items_cleaned: int
    space_freed_mb: float
    errors: List[str]
    warnings: List[str]
    execution_time_seconds: float


class CollectionMaintenanceService:
    """Collection maintenance and cleanup service"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None

        # Maintenance configuration
        self.data_directory = "/data"
        self.temp_directory = "/tmp/mvidarr"
        self.backup_directory = "/data/backups"
        self.max_temp_age_days = 7
        self.min_free_space_gb = 5.0

        # Duplicate detection settings
        self.title_similarity_threshold = 0.8
        self.file_hash_chunk_size = 8192
        self.duplicate_strategy = DuplicateStrategy.KEEP_HIGHEST_QUALITY

        # Cleanup settings
        self.orphaned_file_age_hours = 24
        self.cache_retention_days = 30
        self.log_retention_days = 90

        # Active tasks tracking
        self.active_tasks: Dict[str, MaintenanceTask] = {}

    async def initialize(self):
        """Initialize collection maintenance service"""
        try:
            self.redis_client = await get_redis_client()

            # Ensure directories exist
            os.makedirs(self.temp_directory, exist_ok=True)
            os.makedirs(self.backup_directory, exist_ok=True)

            # Start background cleanup scheduler
            asyncio.create_task(self._maintenance_scheduler_loop())

            logger.info("Collection maintenance service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize collection maintenance service: {e}")
            raise

    async def analyze_storage(self) -> StorageAnalysis:
        """Analyze storage usage and identify cleanup opportunities"""
        try:
            logger.info("Starting storage analysis...")

            # Calculate directory sizes
            total_size = await self._calculate_directory_size(self.data_directory)
            video_size = await self._calculate_directory_size(
                f"{self.data_directory}/videos"
            )
            thumbnail_size = await self._calculate_directory_size(
                f"{self.data_directory}/thumbnails"
            )
            cache_size = await self._calculate_directory_size(
                f"{self.data_directory}/cache"
            )
            temp_size = await self._calculate_directory_size(self.temp_directory)

            # Find orphaned files
            orphaned_size = await self._calculate_orphaned_files_size()

            # Get largest files
            largest_files = await self._find_largest_files(10)
            oldest_files = await self._find_oldest_files(10)

            # Estimate duplicate waste
            duplicate_waste = await self._estimate_duplicate_waste()

            analysis = StorageAnalysis(
                total_size_gb=total_size / (1024**3),
                video_files_size_gb=video_size / (1024**3),
                thumbnail_size_gb=thumbnail_size / (1024**3),
                cache_size_gb=cache_size / (1024**3),
                temp_files_size_gb=temp_size / (1024**3),
                orphaned_files_size_gb=orphaned_size / (1024**3),
                largest_files=largest_files,
                oldest_files=oldest_files,
                duplicate_waste_gb=duplicate_waste / (1024**3),
            )

            logger.info(
                f"Storage analysis completed: {analysis.total_size_gb:.2f}GB total"
            )
            return analysis

        except Exception as e:
            logger.error(f"Failed to analyze storage: {e}")
            return StorageAnalysis(0, 0, 0, 0, 0, 0, [], [], 0)

    async def detect_duplicates(
        self, strategy: DuplicateStrategy = None
    ) -> List[DuplicateGroup]:
        """Detect duplicate videos in collection"""
        try:
            strategy = strategy or self.duplicate_strategy

            logger.info("Starting duplicate detection...")

            # Create maintenance task
            task = await self._create_maintenance_task(
                MaintenanceType.DUPLICATE_DETECTION
            )

            duplicate_groups = []

            try:
                async with get_async_session() as session:
                    # Get all videos for comparison
                    videos_query = select(Video).options(selectinload(Video.artist))
                    result = await session.execute(videos_query)
                    videos = result.scalars().all()

                    task.total_items = len(videos)
                    await self._update_task_progress(task, 0)

                    # Group videos by similar titles
                    title_groups = await self._group_by_similar_titles(videos)

                    # Process each group for duplicates
                    for i, (title_key, video_list) in enumerate(title_groups.items()):
                        if len(video_list) > 1:
                            # Detailed duplicate analysis
                            duplicate_group = await self._analyze_duplicate_group(
                                video_list, strategy
                            )
                            if duplicate_group:
                                duplicate_groups.append(duplicate_group)

                        # Update progress
                        progress = (i + 1) / len(title_groups) * 100
                        await self._update_task_progress(task, progress)

                # Complete task
                task.status = MaintenanceStatus.COMPLETED
                task.completed_at = datetime.now()
                task.results = {
                    "duplicate_groups_found": len(duplicate_groups),
                    "potential_duplicates": sum(
                        len(group.videos) for group in duplicate_groups
                    ),
                    "potential_savings_gb": sum(
                        group.potential_savings_bytes for group in duplicate_groups
                    )
                    / (1024**3),
                }

                await self._update_cached_task(task)

                logger.info(
                    f"Duplicate detection completed: {len(duplicate_groups)} groups found"
                )
                return duplicate_groups

            except Exception as e:
                await self._fail_task(task, str(e))
                raise

        except Exception as e:
            logger.error(f"Failed to detect duplicates: {e}")
            return []

    async def cleanup_broken_links(self) -> CleanupResult:
        """Clean up broken video file links"""
        try:
            start_time = datetime.now()

            logger.info("Starting broken link cleanup...")

            # Create maintenance task
            task = await self._create_maintenance_task(
                MaintenanceType.BROKEN_LINK_CLEANUP
            )

            broken_links = []
            items_cleaned = 0
            errors = []
            warnings = []

            try:
                async with get_async_session() as session:
                    # Get all videos with file paths
                    videos_query = select(Video).where(Video.file_path.isnot(None))
                    result = await session.execute(videos_query)
                    videos = result.scalars().all()

                    task.total_items = len(videos)

                    for i, video in enumerate(videos):
                        try:
                            # Check if file exists
                            if video.file_path and not os.path.exists(video.file_path):
                                broken_links.append(video)

                                # Remove broken video record
                                await session.delete(video)
                                items_cleaned += 1

                                logger.info(
                                    f"Removed broken link: {video.title} ({video.file_path})"
                                )

                        except Exception as e:
                            errors.append(f"Error checking video {video.id}: {str(e)}")

                        # Update progress
                        progress = (i + 1) / len(videos) * 100
                        await self._update_task_progress(task, progress)

                    # Commit changes
                    await session.commit()

                execution_time = (datetime.now() - start_time).total_seconds()

                # Complete task
                task.status = MaintenanceStatus.COMPLETED
                task.completed_at = datetime.now()
                task.results = {
                    "broken_links_found": len(broken_links),
                    "items_cleaned": items_cleaned,
                    "errors": len(errors),
                }

                await self._update_cached_task(task)

                result = CleanupResult(
                    operation="broken_link_cleanup",
                    items_found=len(broken_links),
                    items_cleaned=items_cleaned,
                    space_freed_mb=0,  # No file deletion, just database cleanup
                    errors=errors,
                    warnings=warnings,
                    execution_time_seconds=execution_time,
                )

                logger.info(
                    f"Broken link cleanup completed: {items_cleaned} items cleaned"
                )
                return result

            except Exception as e:
                await self._fail_task(task, str(e))
                raise

        except Exception as e:
            logger.error(f"Failed to cleanup broken links: {e}")
            return CleanupResult("broken_link_cleanup", 0, 0, 0, [str(e)], [], 0)

    async def cleanup_orphaned_files(self) -> CleanupResult:
        """Clean up orphaned files not referenced in database"""
        try:
            start_time = datetime.now()

            logger.info("Starting orphaned files cleanup...")

            # Create maintenance task
            task = await self._create_maintenance_task(MaintenanceType.ORPHANED_FILES)

            orphaned_files = []
            items_cleaned = 0
            space_freed = 0
            errors = []
            warnings = []

            try:
                # Get all file paths from database
                async with get_async_session() as session:
                    videos_query = select(Video.file_path).where(
                        Video.file_path.isnot(None)
                    )
                    result = await session.execute(videos_query)
                    db_file_paths = set(row[0] for row in result.all())

                # Scan video directory
                video_dir = f"{self.data_directory}/videos"
                if os.path.exists(video_dir):
                    all_files = []
                    for root, dirs, files in os.walk(video_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            all_files.append(file_path)

                    task.total_items = len(all_files)

                    # Find orphaned files
                    for i, file_path in enumerate(all_files):
                        try:
                            if file_path not in db_file_paths:
                                # Check file age
                                file_stat = os.stat(file_path)
                                file_age_hours = (
                                    datetime.now().timestamp() - file_stat.st_mtime
                                ) / 3600

                                if file_age_hours > self.orphaned_file_age_hours:
                                    orphaned_files.append(file_path)

                                    # Remove orphaned file
                                    file_size = os.path.getsize(file_path)
                                    os.remove(file_path)

                                    items_cleaned += 1
                                    space_freed += file_size

                                    logger.info(f"Removed orphaned file: {file_path}")
                                else:
                                    warnings.append(
                                        f"Recent orphaned file kept: {file_path}"
                                    )

                        except Exception as e:
                            errors.append(
                                f"Error processing file {file_path}: {str(e)}"
                            )

                        # Update progress
                        progress = (i + 1) / len(all_files) * 100
                        await self._update_task_progress(task, progress)

                execution_time = (datetime.now() - start_time).total_seconds()

                # Complete task
                task.status = MaintenanceStatus.COMPLETED
                task.completed_at = datetime.now()
                task.results = {
                    "orphaned_files_found": len(orphaned_files),
                    "items_cleaned": items_cleaned,
                    "space_freed_mb": space_freed / (1024**2),
                }

                await self._update_cached_task(task)

                result = CleanupResult(
                    operation="orphaned_files_cleanup",
                    items_found=len(orphaned_files),
                    items_cleaned=items_cleaned,
                    space_freed_mb=space_freed / (1024**2),
                    errors=errors,
                    warnings=warnings,
                    execution_time_seconds=execution_time,
                )

                logger.info(
                    f"Orphaned files cleanup completed: {space_freed / (1024**2):.2f}MB freed"
                )
                return result

            except Exception as e:
                await self._fail_task(task, str(e))
                raise

        except Exception as e:
            logger.error(f"Failed to cleanup orphaned files: {e}")
            return CleanupResult("orphaned_files_cleanup", 0, 0, 0, [str(e)], [], 0)

    async def cleanup_cache_files(self) -> CleanupResult:
        """Clean up old cache files"""
        try:
            start_time = datetime.now()

            logger.info("Starting cache cleanup...")

            items_found = 0
            items_cleaned = 0
            space_freed = 0
            errors = []
            warnings = []

            # Clean up various cache directories
            cache_directories = [
                f"{self.data_directory}/cache",
                f"{self.data_directory}/thumbnails/cache",
                self.temp_directory,
            ]

            cutoff_date = datetime.now() - timedelta(days=self.cache_retention_days)

            for cache_dir in cache_directories:
                if os.path.exists(cache_dir):
                    for root, dirs, files in os.walk(cache_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                file_stat = os.stat(file_path)
                                file_mtime = datetime.fromtimestamp(file_stat.st_mtime)

                                items_found += 1

                                if file_mtime < cutoff_date:
                                    file_size = file_stat.st_size
                                    os.remove(file_path)

                                    items_cleaned += 1
                                    space_freed += file_size

                            except Exception as e:
                                errors.append(
                                    f"Error processing cache file {file_path}: {str(e)}"
                                )

            execution_time = (datetime.now() - start_time).total_seconds()

            result = CleanupResult(
                operation="cache_cleanup",
                items_found=items_found,
                items_cleaned=items_cleaned,
                space_freed_mb=space_freed / (1024**2),
                errors=errors,
                warnings=warnings,
                execution_time_seconds=execution_time,
            )

            logger.info(
                f"Cache cleanup completed: {space_freed / (1024**2):.2f}MB freed"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to cleanup cache files: {e}")
            return CleanupResult("cache_cleanup", 0, 0, 0, [str(e)], [], 0)

    async def optimize_storage(self) -> Dict[str, Any]:
        """Optimize storage usage through various methods"""
        try:
            logger.info("Starting storage optimization...")

            optimization_results = []

            # 1. Clean up broken links
            broken_link_result = await self.cleanup_broken_links()
            optimization_results.append(("broken_links", broken_link_result.__dict__))

            # 2. Clean up orphaned files
            orphaned_result = await self.cleanup_orphaned_files()
            optimization_results.append(("orphaned_files", orphaned_result.__dict__))

            # 3. Clean up cache files
            cache_result = await self.cleanup_cache_files()
            optimization_results.append(("cache_cleanup", cache_result.__dict__))

            # 4. Remove duplicate files (if configured)
            if self.duplicate_strategy != DuplicateStrategy.MANUAL_REVIEW:
                duplicate_result = await self._cleanup_duplicates_automatically()
                optimization_results.append(("duplicates", duplicate_result))

            # Calculate total savings
            total_space_freed = sum(
                result[1].get("space_freed_mb", 0) for result in optimization_results
            )

            return {
                "optimization_results": optimization_results,
                "total_space_freed_mb": total_space_freed,
                "optimized_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to optimize storage: {e}")
            return {"error": str(e)}

    async def get_maintenance_tasks(self) -> List[MaintenanceTask]:
        """Get list of maintenance tasks"""
        try:
            # Get active tasks
            tasks = list(self.active_tasks.values())

            # Get recent completed tasks from cache
            cached_tasks = await self._get_cached_completed_tasks()
            tasks.extend(cached_tasks)

            # Sort by start time (newest first)
            tasks.sort(key=lambda t: t.started_at, reverse=True)

            return tasks[:20]  # Return last 20 tasks

        except Exception as e:
            logger.error(f"Failed to get maintenance tasks: {e}")
            return []

    async def cancel_maintenance_task(self, task_id: str) -> bool:
        """Cancel running maintenance task"""
        try:
            task = self.active_tasks.get(task_id)
            if task and task.status == MaintenanceStatus.RUNNING:
                task.status = MaintenanceStatus.CANCELLED
                task.completed_at = datetime.now()
                await self._update_cached_task(task)

                logger.info(f"Cancelled maintenance task {task_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to cancel maintenance task {task_id}: {e}")
            return False

    async def _calculate_directory_size(self, directory: str) -> int:
        """Calculate total size of directory in bytes"""
        try:
            if not os.path.exists(directory):
                return 0

            total_size = 0
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        continue

            return total_size

        except Exception as e:
            logger.error(f"Failed to calculate directory size for {directory}: {e}")
            return 0

    async def _calculate_orphaned_files_size(self) -> int:
        """Calculate size of orphaned files"""
        try:
            # Get database file paths
            async with get_async_session() as session:
                videos_query = select(Video.file_path).where(
                    Video.file_path.isnot(None)
                )
                result = await session.execute(videos_query)
                db_file_paths = set(row[0] for row in result.all())

            # Calculate orphaned file size
            orphaned_size = 0
            video_dir = f"{self.data_directory}/videos"

            if os.path.exists(video_dir):
                for root, dirs, files in os.walk(video_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if file_path not in db_file_paths:
                            try:
                                orphaned_size += os.path.getsize(file_path)
                            except (OSError, IOError):
                                continue

            return orphaned_size

        except Exception as e:
            logger.error(f"Failed to calculate orphaned files size: {e}")
            return 0

    async def _find_largest_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Find largest files in collection"""
        try:
            async with get_async_session() as session:
                query = (
                    select(Video.id, Video.title, Video.file_path, Video.file_size)
                    .where(Video.file_size.isnot(None))
                    .order_by(desc(Video.file_size))
                    .limit(limit)
                )

                result = await session.execute(query)
                files = []

                for row in result.all():
                    files.append(
                        {
                            "video_id": row[0],
                            "title": row[1],
                            "file_path": row[2],
                            "size_mb": (row[3] or 0) / (1024**2),
                        }
                    )

                return files

        except Exception as e:
            logger.error(f"Failed to find largest files: {e}")
            return []

    async def _find_oldest_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Find oldest files in collection"""
        try:
            async with get_async_session() as session:
                query = (
                    select(Video.id, Video.title, Video.file_path, Video.created_at)
                    .order_by(asc(Video.created_at))
                    .limit(limit)
                )

                result = await session.execute(query)
                files = []

                for row in result.all():
                    files.append(
                        {
                            "video_id": row[0],
                            "title": row[1],
                            "file_path": row[2],
                            "created_at": row[3].isoformat() if row[3] else None,
                        }
                    )

                return files

        except Exception as e:
            logger.error(f"Failed to find oldest files: {e}")
            return []

    async def _estimate_duplicate_waste(self) -> int:
        """Estimate storage waste from duplicates"""
        try:
            duplicates = await self.detect_duplicates()
            total_waste = sum(group.potential_savings_bytes for group in duplicates)
            return total_waste

        except Exception as e:
            logger.error(f"Failed to estimate duplicate waste: {e}")
            return 0

    async def _group_by_similar_titles(
        self, videos: List[Video]
    ) -> Dict[str, List[Video]]:
        """Group videos by similar titles"""
        try:
            from difflib import SequenceMatcher

            groups = {}
            processed = set()

            for i, video in enumerate(videos):
                if video.id in processed:
                    continue

                # Create group with this video
                group_key = f"group_{i}"
                groups[group_key] = [video]
                processed.add(video.id)

                # Find similar videos
                for other_video in videos[i + 1 :]:
                    if other_video.id in processed:
                        continue

                    # Calculate title similarity
                    similarity = SequenceMatcher(
                        None,
                        (video.title or "").lower(),
                        (other_video.title or "").lower(),
                    ).ratio()

                    if similarity >= self.title_similarity_threshold:
                        groups[group_key].append(other_video)
                        processed.add(other_video.id)

            # Filter groups with only one video
            return {k: v for k, v in groups.items() if len(v) > 1}

        except Exception as e:
            logger.error(f"Failed to group by similar titles: {e}")
            return {}

    async def _analyze_duplicate_group(
        self, videos: List[Video], strategy: DuplicateStrategy
    ) -> Optional[DuplicateGroup]:
        """Analyze a group of potential duplicates"""
        try:
            if len(videos) < 2:
                return None

            # Calculate similarity score
            title_similarity = 0.9  # Simplified

            # Determine recommended keeper based on strategy
            recommended_keeper = videos[0].id
            if strategy == DuplicateStrategy.KEEP_HIGHEST_QUALITY:
                # Keep the one with highest quality (simplified)
                recommended_keeper = max(videos, key=lambda v: v.file_size or 0).id
            elif strategy == DuplicateStrategy.KEEP_NEWEST:
                recommended_keeper = max(
                    videos, key=lambda v: v.created_at or datetime.min
                ).id
            elif strategy == DuplicateStrategy.KEEP_MOST_WATCHED:
                recommended_keeper = max(videos, key=lambda v: v.view_count or 0).id

            # Calculate potential savings
            total_size = sum(v.file_size or 0 for v in videos)
            keeper_size = next(
                (v.file_size or 0 for v in videos if v.id == recommended_keeper), 0
            )
            potential_savings = total_size - keeper_size

            group_id = f"dup_{hashlib.md5(''.join(str(v.id) for v in videos).encode()).hexdigest()[:8]}"

            return DuplicateGroup(
                group_id=group_id,
                title_similarity=title_similarity,
                videos=[
                    {
                        "id": v.id,
                        "title": v.title,
                        "file_path": v.file_path,
                        "file_size": v.file_size or 0,
                        "created_at": (
                            v.created_at.isoformat() if v.created_at else None
                        ),
                        "view_count": v.view_count or 0,
                    }
                    for v in videos
                ],
                recommended_keeper=recommended_keeper,
                total_size_bytes=total_size,
                potential_savings_bytes=potential_savings,
                duplicate_reason="Similar title and metadata",
            )

        except Exception as e:
            logger.error(f"Failed to analyze duplicate group: {e}")
            return None

    async def _create_maintenance_task(
        self, task_type: MaintenanceType
    ) -> MaintenanceTask:
        """Create a new maintenance task"""
        task_id = f"task_{int(datetime.now().timestamp())}_{task_type.value}"

        task = MaintenanceTask(
            task_id=task_id,
            task_type=task_type,
            status=MaintenanceStatus.RUNNING,
            progress_percent=0.0,
            items_processed=0,
            total_items=0,
            started_at=datetime.now(),
            completed_at=None,
            error_message=None,
            results={},
        )

        self.active_tasks[task_id] = task
        await self._cache_task(task)

        return task

    async def _update_task_progress(self, task: MaintenanceTask, progress: float):
        """Update task progress"""
        task.progress_percent = progress
        await self._update_cached_task(task)

    async def _fail_task(self, task: MaintenanceTask, error_message: str):
        """Mark task as failed"""
        task.status = MaintenanceStatus.FAILED
        task.completed_at = datetime.now()
        task.error_message = error_message
        await self._update_cached_task(task)

    async def _cleanup_duplicates_automatically(self) -> Dict[str, Any]:
        """Automatically cleanup duplicates based on strategy"""
        # Placeholder implementation
        return {"duplicates_removed": 0, "space_freed_mb": 0.0}

    async def _maintenance_scheduler_loop(self):
        """Background maintenance scheduler"""
        while True:
            try:
                # Run daily maintenance at 3 AM
                now = datetime.now()
                if now.hour == 3 and now.minute == 0:
                    logger.info("Running scheduled maintenance...")

                    # Run cache cleanup
                    await self.cleanup_cache_files()

                    # Check for low disk space
                    await self._check_disk_space()

                # Sleep for 1 hour
                await asyncio.sleep(3600)

            except Exception as e:
                logger.error(f"Maintenance scheduler loop failed: {e}")
                await asyncio.sleep(3600)

    async def _check_disk_space(self):
        """Check available disk space"""
        try:
            import shutil

            total, used, free = shutil.disk_usage(self.data_directory)
            free_gb = free / (1024**3)

            if free_gb < self.min_free_space_gb:
                logger.warning(f"Low disk space: {free_gb:.2f}GB remaining")

                # Trigger automatic cleanup
                await self.cleanup_cache_files()

        except Exception as e:
            logger.error(f"Failed to check disk space: {e}")

    async def _cache_task(self, task: MaintenanceTask):
        """Cache maintenance task"""
        try:
            cache_key = f"maintenance_task:{task.task_id}"
            task_data = {
                "task_id": task.task_id,
                "task_type": task.task_type.value,
                "status": task.status.value,
                "progress_percent": task.progress_percent,
                "items_processed": task.items_processed,
                "total_items": task.total_items,
                "started_at": task.started_at.isoformat(),
                "completed_at": (
                    task.completed_at.isoformat() if task.completed_at else None
                ),
                "error_message": task.error_message,
                "results": task.results,
            }

            await self.redis_client.setex(cache_key, 86400, json.dumps(task_data))
            await self.redis_client.sadd("maintenance_tasks", task.task_id)

        except Exception as e:
            logger.error(f"Failed to cache maintenance task {task.task_id}: {e}")

    async def _update_cached_task(self, task: MaintenanceTask):
        """Update cached maintenance task"""
        await self._cache_task(task)

    async def _get_cached_completed_tasks(self) -> List[MaintenanceTask]:
        """Get cached completed maintenance tasks"""
        try:
            task_ids = await self.redis_client.smembers("maintenance_tasks")
            tasks = []

            for task_id in task_ids:
                if task_id not in self.active_tasks:  # Don't duplicate active tasks
                    cache_key = f"maintenance_task:{task_id}"
                    task_data = await self.redis_client.get(cache_key)

                    if task_data:
                        data = json.loads(task_data)
                        task = MaintenanceTask(
                            task_id=data["task_id"],
                            task_type=MaintenanceType(data["task_type"]),
                            status=MaintenanceStatus(data["status"]),
                            progress_percent=data["progress_percent"],
                            items_processed=data["items_processed"],
                            total_items=data["total_items"],
                            started_at=datetime.fromisoformat(data["started_at"]),
                            completed_at=(
                                datetime.fromisoformat(data["completed_at"])
                                if data.get("completed_at")
                                else None
                            ),
                            error_message=data.get("error_message"),
                            results=data.get("results", {}),
                        )
                        tasks.append(task)

            return tasks

        except Exception as e:
            logger.error(f"Failed to get cached completed tasks: {e}")
            return []


# Global service instance
_collection_maintenance_service = None


async def get_collection_maintenance_service(
    config: Optional[Dict] = None,
) -> CollectionMaintenanceService:
    """Get global collection maintenance service instance"""
    global _collection_maintenance_service

    if _collection_maintenance_service is None:
        _collection_maintenance_service = CollectionMaintenanceService(config)
        await _collection_maintenance_service.initialize()

    return _collection_maintenance_service
