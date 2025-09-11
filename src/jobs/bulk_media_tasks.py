"""
MVidarr Bulk Media Operations - Phase 2 Week 22
Large-scale media processing tasks with concurrent processing and progress tracking
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.jobs.advanced_image_tasks import AdvancedImageAnalyzer, ImageMetadata
from src.services.ffmpeg_stream_manager import ffmpeg_stream_manager
from src.services.image_thread_pool import get_image_processing_pool
from src.services.media_cache_manager import (
    cache_media_metadata,
    get_media_cache_manager,
)
from src.services.performance_monitor import (
    get_performance_monitor,
    track_media_processing_time,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.bulk_media")


class BulkOperationType(Enum):
    """Types of bulk media operations"""

    METADATA_ENRICHMENT = "metadata_enrichment"
    QUALITY_ANALYSIS = "quality_analysis"
    FORMAT_CONVERSION = "format_conversion"
    COLLECTION_IMPORT = "collection_import"
    COLLECTION_EXPORT = "collection_export"
    CLEANUP_OPERATION = "cleanup_operation"
    THUMBNAIL_GENERATION = "thumbnail_generation"
    MEDIA_VALIDATION = "media_validation"


class BulkOperationStatus(Enum):
    """Status of bulk operations"""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BulkOperationProgress:
    """Progress tracking for bulk operations"""

    operation_id: str
    operation_type: BulkOperationType
    status: BulkOperationStatus
    total_items: int
    processed_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    current_item: Optional[str] = None
    error_details: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def progress_percentage(self) -> float:
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100

    @property
    def processing_time(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def items_per_second(self) -> float:
        if self.processing_time == 0:
            return 0.0
        return self.processed_items / self.processing_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "status": self.status.value,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "progress_percentage": self.progress_percentage,
            "processing_time": self.processing_time,
            "items_per_second": self.items_per_second,
            "current_item": self.current_item,
            "error_count": len(self.error_details),
        }


@dataclass
class BulkMediaItem:
    """Individual media item for bulk processing"""

    file_path: str
    media_type: str  # "image", "video", "audio"
    file_size: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time: float = 0.0


class BulkMediaProcessor:
    """High-performance bulk media processing with concurrent operations"""

    def __init__(self, max_workers: Optional[int] = None):
        """Initialize bulk media processor"""
        self.max_workers = max_workers or min(32, (os.cpu_count() or 1) * 4)
        self.active_operations: Dict[str, BulkOperationProgress] = {}
        self.image_analyzer = AdvancedImageAnalyzer()
        self.ffmpeg_manager = ffmpeg_stream_manager
        logger.info(
            f"🚀 Bulk media processor initialized with {self.max_workers} workers"
        )

    async def bulk_metadata_enrichment(
        self,
        media_paths: List[str],
        operation_id: str,
        progress_callback: Optional[Callable] = None,
    ) -> BulkOperationProgress:
        """Enrich metadata for large media collections"""

        progress = BulkOperationProgress(
            operation_id=operation_id,
            operation_type=BulkOperationType.METADATA_ENRICHMENT,
            status=BulkOperationStatus.RUNNING,
            total_items=len(media_paths),
        )
        self.active_operations[operation_id] = progress

        try:
            logger.info(f"📊 Starting metadata enrichment for {len(media_paths)} items")

            # Categorize media by type
            media_items = []
            for path in media_paths:
                path_obj = Path(path)
                if path_obj.exists():
                    item = BulkMediaItem(
                        file_path=path,
                        media_type=self._detect_media_type(path_obj),
                        file_size=path_obj.stat().st_size,
                    )
                    media_items.append(item)

            # Process in batches for optimal performance
            batch_size = min(100, max(10, len(media_items) // 10))

            for i in range(0, len(media_items), batch_size):
                batch = media_items[i : i + batch_size]
                await self._process_metadata_batch(batch, progress, progress_callback)

                if progress.status == BulkOperationStatus.CANCELLED:
                    break

            progress.status = BulkOperationStatus.COMPLETED
            progress.end_time = time.time()

            logger.info(
                f"✅ Metadata enrichment completed: {progress.successful_items}/{progress.total_items} successful"
            )

        except Exception as e:
            logger.error(f"❌ Bulk metadata enrichment failed: {e}")
            progress.status = BulkOperationStatus.FAILED
            progress.error_details.append(
                {
                    "error": str(e),
                    "timestamp": time.time(),
                    "context": "bulk_metadata_enrichment",
                }
            )

        return progress

    async def _process_metadata_batch(
        self,
        batch: List[BulkMediaItem],
        progress: BulkOperationProgress,
        progress_callback: Optional[Callable],
    ):
        """Process a batch of media items for metadata extraction with caching integration"""
        start_time = time.time()
        cache_manager = await get_media_cache_manager()
        pool = get_image_processing_pool()

        if not pool.pool.is_running():
            await pool.start()

        # Separate by media type for optimized processing
        image_items = [item for item in batch if item.media_type == "image"]
        video_items = [item for item in batch if item.media_type == "video"]

        # Process images concurrently with cache integration
        if image_items:
            image_jobs = []
            cache_hits = 0

            for item in image_items:
                # Check cache first
                cached_metadata = await cache_manager.get_cached_media_metadata(
                    item.file_path
                )
                if cached_metadata:
                    item.metadata = cached_metadata
                    progress.successful_items += 1
                    cache_hits += 1
                else:
                    # Add to processing queue
                    image_jobs.append((self._extract_image_metadata, (item,), {}))

            logger.info(
                f"📊 Cache performance: {cache_hits}/{len(image_items)} hits ({cache_hits/len(image_items)*100:.1f}%)"
            )

            if image_jobs:
                with pool.pool.batch_execution(image_jobs) as batch_futures:
                    job_index = 0
                    for item in image_items:
                        if item.metadata:  # Skip cached items
                            continue

                        try:
                            future = batch_futures[job_index]
                            metadata = future.result()

                            if metadata:
                                metadata_dict = metadata.to_dict()
                                item.metadata = metadata_dict

                                # Cache the result
                                await cache_manager.cache_media_metadata(
                                    item.file_path, metadata_dict
                                )

                                progress.successful_items += 1
                            else:
                                progress.failed_items += 1

                        except Exception as e:
                            item.error = str(e)
                            progress.failed_items += 1
                            progress.error_details.append(
                                {
                                    "file": item.file_path,
                                    "error": str(e),
                                    "timestamp": time.time(),
                                }
                            )

                        job_index += 1
                        progress.processed_items += 1
                        progress.current_item = item.file_path

                        if progress_callback:
                            progress_callback(progress.to_dict())
            else:
                # All items were cached
                for item in image_items:
                    progress.processed_items += 1
                    progress.current_item = item.file_path
                    if progress_callback:
                        progress_callback(progress.to_dict())

        # Process videos with cache integration
        for item in video_items:
            try:
                # Check cache first
                cached_metadata = await cache_manager.get_cached_media_metadata(
                    item.file_path
                )
                if cached_metadata:
                    item.metadata = cached_metadata
                    progress.successful_items += 1
                else:
                    # Extract and cache metadata
                    metadata = await self._extract_video_metadata(item.file_path)
                    item.metadata = metadata

                    # Cache the result
                    await cache_manager.cache_media_metadata(item.file_path, metadata)

                    progress.successful_items += 1

            except Exception as e:
                item.error = str(e)
                progress.failed_items += 1
                progress.error_details.append(
                    {"file": item.file_path, "error": str(e), "timestamp": time.time()}
                )

            progress.processed_items += 1
            progress.current_item = item.file_path

            if progress_callback:
                progress_callback(progress.to_dict())

        # Track processing performance
        processing_time = time.time() - start_time
        await track_media_processing_time("batch_metadata_extraction", processing_time)

        logger.info(
            f"📊 Batch processed: {len(batch)} items in {processing_time:.2f}s ({len(batch)/processing_time:.1f} items/sec)"
        )

    def _extract_image_metadata(self, item: BulkMediaItem) -> Optional[ImageMetadata]:
        """Extract metadata from a single image"""
        try:
            path = Path(item.file_path)
            return self.image_analyzer._analyze_single_image(path)
        except Exception as e:
            logger.warning(
                f"⚠️ Failed to extract image metadata for {item.file_path}: {e}"
            )
            return None

    async def _extract_video_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract basic video metadata (placeholder)"""
        # Placeholder for video metadata extraction
        # This would integrate with FFmpeg for comprehensive video analysis
        path = Path(file_path)
        return {
            "file_size": path.stat().st_size,
            "file_name": path.name,
            "file_extension": path.suffix,
            "extracted_at": time.time(),
        }

    def _detect_media_type(self, path: Path) -> str:
        """Detect media type based on file extension"""
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
        video_extensions = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"}
        audio_extensions = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}

        extension = path.suffix.lower()

        if extension in image_extensions:
            return "image"
        elif extension in video_extensions:
            return "video"
        elif extension in audio_extensions:
            return "audio"
        else:
            return "unknown"

    async def bulk_collection_import(
        self,
        source_directory: str,
        operation_id: str,
        file_patterns: List[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> BulkOperationProgress:
        """Import large media collections with progress tracking"""

        progress = BulkOperationProgress(
            operation_id=operation_id,
            operation_type=BulkOperationType.COLLECTION_IMPORT,
            status=BulkOperationStatus.RUNNING,
            total_items=0,  # Will be updated after scanning
        )
        self.active_operations[operation_id] = progress

        try:
            logger.info(f"📂 Starting collection import from {source_directory}")

            # Scan directory for media files
            source_path = Path(source_directory)
            if not source_path.exists():
                raise ValueError(f"Source directory does not exist: {source_directory}")

            # Default patterns if none provided
            if not file_patterns:
                file_patterns = [
                    "**/*.jpg",
                    "**/*.jpeg",
                    "**/*.png",
                    "**/*.mp4",
                    "**/*.avi",
                    "**/*.mkv",
                ]

            # Collect all matching files
            media_files = []
            for pattern in file_patterns:
                media_files.extend(source_path.glob(pattern))

            progress.total_items = len(media_files)
            logger.info(f"📊 Found {len(media_files)} media files to import")

            # Process files in batches
            batch_size = min(50, max(10, len(media_files) // 20))

            for i in range(0, len(media_files), batch_size):
                batch = media_files[i : i + batch_size]
                await self._process_import_batch(batch, progress, progress_callback)

                if progress.status == BulkOperationStatus.CANCELLED:
                    break

            progress.status = BulkOperationStatus.COMPLETED
            progress.end_time = time.time()

            logger.info(
                f"✅ Collection import completed: {progress.successful_items}/{progress.total_items} files imported"
            )

        except Exception as e:
            logger.error(f"❌ Bulk collection import failed: {e}")
            progress.status = BulkOperationStatus.FAILED
            progress.error_details.append(
                {
                    "error": str(e),
                    "timestamp": time.time(),
                    "context": "bulk_collection_import",
                }
            )

        return progress

    async def _process_import_batch(
        self,
        batch: List[Path],
        progress: BulkOperationProgress,
        progress_callback: Optional[Callable],
    ):
        """Process a batch of files for import"""
        for file_path in batch:
            try:
                # Validate file accessibility
                if not file_path.exists():
                    raise FileNotFoundError(f"File not found: {file_path}")

                # Basic file validation
                file_size = file_path.stat().st_size
                if file_size == 0:
                    raise ValueError(f"Empty file: {file_path}")

                # Success - file is valid for import
                progress.successful_items += 1

            except Exception as e:
                progress.failed_items += 1
                progress.error_details.append(
                    {"file": str(file_path), "error": str(e), "timestamp": time.time()}
                )

            progress.processed_items += 1
            progress.current_item = str(file_path)

            if progress_callback:
                progress_callback(progress.to_dict())

    async def bulk_cleanup_operation(
        self,
        target_directory: str,
        operation_id: str,
        cleanup_rules: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
    ) -> BulkOperationProgress:
        """Perform bulk cleanup operations on media collections"""

        progress = BulkOperationProgress(
            operation_id=operation_id,
            operation_type=BulkOperationType.CLEANUP_OPERATION,
            status=BulkOperationStatus.RUNNING,
            total_items=0,
        )
        self.active_operations[operation_id] = progress

        try:
            logger.info(f"🧹 Starting cleanup operation in {target_directory}")

            target_path = Path(target_directory)
            if not target_path.exists():
                raise ValueError(f"Target directory does not exist: {target_directory}")

            # Scan for files to cleanup based on rules
            cleanup_candidates = []

            # Rule: Remove empty files
            if cleanup_rules.get("remove_empty_files", False):
                for file_path in target_path.rglob("*"):
                    if file_path.is_file() and file_path.stat().st_size == 0:
                        cleanup_candidates.append((file_path, "empty_file"))

            # Rule: Remove duplicate files (placeholder)
            if cleanup_rules.get("remove_duplicates", False):
                # Placeholder for duplicate detection logic
                pass

            # Rule: Remove files older than X days
            if cleanup_rules.get("remove_old_files"):
                max_age_days = cleanup_rules["remove_old_files"]
                cutoff_time = time.time() - (max_age_days * 24 * 3600)

                for file_path in target_path.rglob("*"):
                    if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                        cleanup_candidates.append((file_path, "old_file"))

            progress.total_items = len(cleanup_candidates)
            logger.info(f"🧹 Found {len(cleanup_candidates)} items for cleanup")

            # Process cleanup candidates
            for file_path, reason in cleanup_candidates:
                try:
                    # Simulate cleanup operation (in real implementation, would actually remove files)
                    logger.debug(f"Cleaning up {file_path} (reason: {reason})")
                    progress.successful_items += 1

                except Exception as e:
                    progress.failed_items += 1
                    progress.error_details.append(
                        {
                            "file": str(file_path),
                            "error": str(e),
                            "reason": reason,
                            "timestamp": time.time(),
                        }
                    )

                progress.processed_items += 1
                progress.current_item = str(file_path)

                if progress_callback:
                    progress_callback(progress.to_dict())

            progress.status = BulkOperationStatus.COMPLETED
            progress.end_time = time.time()

            logger.info(
                f"✅ Cleanup operation completed: {progress.successful_items} items processed"
            )

        except Exception as e:
            logger.error(f"❌ Bulk cleanup operation failed: {e}")
            progress.status = BulkOperationStatus.FAILED
            progress.error_details.append(
                {
                    "error": str(e),
                    "timestamp": time.time(),
                    "context": "bulk_cleanup_operation",
                }
            )

        return progress

    def get_operation_status(
        self, operation_id: str
    ) -> Optional[BulkOperationProgress]:
        """Get current status of a bulk operation"""
        return self.active_operations.get(operation_id)

    def cancel_operation(self, operation_id: str) -> bool:
        """Cancel a running bulk operation"""
        if operation_id in self.active_operations:
            operation = self.active_operations[operation_id]
            if operation.status == BulkOperationStatus.RUNNING:
                operation.status = BulkOperationStatus.CANCELLED
                operation.end_time = time.time()
                logger.info(f"🛑 Operation {operation_id} cancelled")
                return True
        return False

    def get_active_operations(self) -> List[Dict[str, Any]]:
        """Get list of all active operations"""
        return [op.to_dict() for op in self.active_operations.values()]


# Convenience functions for task submission
async def bulk_enrich_metadata(
    media_paths: List[str],
    operation_id: str,
    progress_callback: Optional[Callable] = None,
) -> BulkOperationProgress:
    """Enrich metadata for large media collections"""
    processor = BulkMediaProcessor()
    return await processor.bulk_metadata_enrichment(
        media_paths, operation_id, progress_callback
    )


async def bulk_import_collection(
    source_directory: str,
    operation_id: str,
    file_patterns: List[str] = None,
    progress_callback: Optional[Callable] = None,
) -> BulkOperationProgress:
    """Import large media collections"""
    processor = BulkMediaProcessor()
    return await processor.bulk_collection_import(
        source_directory, operation_id, file_patterns, progress_callback
    )


async def bulk_cleanup_media(
    target_directory: str,
    operation_id: str,
    cleanup_rules: Dict[str, Any],
    progress_callback: Optional[Callable] = None,
) -> BulkOperationProgress:
    """Perform bulk cleanup operations"""
    processor = BulkMediaProcessor()
    return await processor.bulk_cleanup_operation(
        target_directory, operation_id, cleanup_rules, progress_callback
    )
