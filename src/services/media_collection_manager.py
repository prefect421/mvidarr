"""
MVidarr Media Collection Manager - Phase 2 Week 22
Advanced collection processing management with concurrent operations and resource optimization
"""

import hashlib
import json
import mimetypes
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.jobs.bulk_media_tasks import BulkMediaProcessor
from src.services.redis_manager import RedisManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.collection_manager")


class CollectionType(Enum):
    """Types of media collections"""

    IMAGE_COLLECTION = "image_collection"
    VIDEO_COLLECTION = "video_collection"
    MIXED_COLLECTION = "mixed_collection"
    ARTIST_COLLECTION = "artist_collection"
    PLAYLIST_COLLECTION = "playlist_collection"


class ProcessingPriority(Enum):
    """Processing priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class CollectionMetadata:
    """Metadata for media collections"""

    collection_id: str
    collection_type: CollectionType
    name: str
    description: str = ""
    total_items: int = 0
    total_size_bytes: int = 0
    created_at: float = field(default_factory=time.time)
    last_modified: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    custom_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "collection_type": self.collection_type.value,
            "name": self.name,
            "description": self.description,
            "total_items": self.total_items,
            "total_size_bytes": self.total_size_bytes,
            "created_at": self.created_at,
            "last_modified": self.last_modified,
            "tags": self.tags,
            "custom_attributes": self.custom_attributes,
        }


@dataclass
class CollectionProcessingConfig:
    """Configuration for collection processing"""

    max_concurrent_operations: int = 10
    batch_size: int = 100
    memory_limit_mb: int = 2048
    processing_priority: ProcessingPriority = ProcessingPriority.NORMAL
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600
    retry_failed_items: bool = True
    max_retries: int = 3
    progress_update_interval: float = 1.0  # seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_concurrent_operations": self.max_concurrent_operations,
            "batch_size": self.batch_size,
            "memory_limit_mb": self.memory_limit_mb,
            "processing_priority": self.processing_priority.value,
            "enable_caching": self.enable_caching,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "retry_failed_items": self.retry_failed_items,
            "max_retries": self.max_retries,
            "progress_update_interval": self.progress_update_interval,
        }


class MediaCollectionManager:
    """Advanced media collection processing with resource optimization and caching"""

    def __init__(self, config: Optional[CollectionProcessingConfig] = None):
        """Initialize media collection manager"""
        self.config = config or CollectionProcessingConfig()
        self.bulk_processor = BulkMediaProcessor()
        self.redis_manager = RedisManager()

        # Resource management
        self.active_collections: Dict[str, CollectionMetadata] = {}
        self.processing_queues: Dict[ProcessingPriority, List[str]] = {
            priority: [] for priority in ProcessingPriority
        }

        # Performance tracking
        self.processing_stats = {
            "collections_processed": 0,
            "total_items_processed": 0,
            "average_processing_time": 0.0,
            "cache_hit_ratio": 0.0,
        }

        logger.info(
            f"📊 Media collection manager initialized with config: {self.config.to_dict()}"
        )

    async def create_collection(
        self,
        collection_id: str,
        name: str,
        collection_type: CollectionType,
        description: str = "",
        tags: List[str] = None,
        custom_attributes: Dict[str, Any] = None,
    ) -> CollectionMetadata:
        """Create a new media collection"""

        if collection_id in self.active_collections:
            raise ValueError(f"Collection {collection_id} already exists")

        metadata = CollectionMetadata(
            collection_id=collection_id,
            collection_type=collection_type,
            name=name,
            description=description,
            tags=tags or [],
            custom_attributes=custom_attributes or {},
        )

        self.active_collections[collection_id] = metadata

        # Cache collection metadata
        if self.config.enable_caching:
            await self.redis_manager.set(
                f"collection:{collection_id}:metadata",
                json.dumps(metadata.to_dict()),
                ttl=self.config.cache_ttl_seconds,
            )

        logger.info(f"📁 Created collection: {name} ({collection_id})")
        return metadata

    async def add_media_to_collection(
        self, collection_id: str, media_paths: List[str], validate_files: bool = True
    ) -> Dict[str, Any]:
        """Add media files to a collection with validation"""

        if collection_id not in self.active_collections:
            raise ValueError(f"Collection {collection_id} not found")

        collection = self.active_collections[collection_id]

        # Validate media files if requested
        valid_files = []
        invalid_files = []
        total_size = 0

        for media_path in media_paths:
            try:
                path = Path(media_path)
                if validate_files:
                    if not path.exists():
                        invalid_files.append(
                            {"path": media_path, "error": "File not found"}
                        )
                        continue

                    if path.stat().st_size == 0:
                        invalid_files.append(
                            {"path": media_path, "error": "Empty file"}
                        )
                        continue

                    # Check if it's a valid media file
                    mime_type, _ = mimetypes.guess_type(str(path))
                    if not mime_type or not any(
                        mime_type.startswith(t) for t in ["image/", "video/", "audio/"]
                    ):
                        invalid_files.append(
                            {"path": media_path, "error": "Not a valid media file"}
                        )
                        continue

                valid_files.append(media_path)
                total_size += path.stat().st_size

            except Exception as e:
                invalid_files.append({"path": media_path, "error": str(e)})

        # Update collection metadata
        collection.total_items += len(valid_files)
        collection.total_size_bytes += total_size
        collection.last_modified = time.time()

        # Update cache
        if self.config.enable_caching:
            await self.redis_manager.set(
                f"collection:{collection_id}:metadata",
                json.dumps(collection.to_dict()),
                ttl=self.config.cache_ttl_seconds,
            )

        result = {
            "collection_id": collection_id,
            "added_files": len(valid_files),
            "invalid_files": len(invalid_files),
            "total_size_added": total_size,
            "validation_errors": invalid_files,
        }

        logger.info(f"📂 Added {len(valid_files)} files to collection {collection_id}")
        return result

    async def process_collection_metadata(
        self,
        collection_id: str,
        media_paths: List[str],
        priority: ProcessingPriority = ProcessingPriority.NORMAL,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Process metadata for an entire collection"""

        if collection_id not in self.active_collections:
            raise ValueError(f"Collection {collection_id} not found")

        operation_id = f"{collection_id}_metadata_{int(time.time())}"

        # Queue operation based on priority
        if priority != ProcessingPriority.URGENT:
            self.processing_queues[priority].append(operation_id)
            logger.info(
                f"⏳ Queued metadata processing for collection {collection_id} (priority: {priority.value})"
            )

        # Execute metadata enrichment
        start_time = time.time()

        try:
            # Use bulk processor for metadata enrichment
            progress = await self.bulk_processor.bulk_metadata_enrichment(
                media_paths=media_paths,
                operation_id=operation_id,
                progress_callback=progress_callback,
            )

            processing_time = time.time() - start_time

            # Update collection metadata
            collection = self.active_collections[collection_id]
            collection.last_modified = time.time()

            # Update processing stats
            self.processing_stats["collections_processed"] += 1
            self.processing_stats["total_items_processed"] += len(media_paths)
            self.processing_stats["average_processing_time"] = (
                self.processing_stats["average_processing_time"]
                * (self.processing_stats["collections_processed"] - 1)
                + processing_time
            ) / self.processing_stats["collections_processed"]

            result = {
                "collection_id": collection_id,
                "operation_id": operation_id,
                "status": progress.status.value,
                "processed_items": progress.processed_items,
                "successful_items": progress.successful_items,
                "failed_items": progress.failed_items,
                "processing_time": processing_time,
                "items_per_second": progress.items_per_second,
            }

            # Cache results
            if self.config.enable_caching:
                await self.redis_manager.set(
                    f"collection:{collection_id}:processing_result",
                    json.dumps(result),
                    ttl=self.config.cache_ttl_seconds,
                )

            logger.info(f"✅ Collection metadata processing completed: {result}")
            return result

        except Exception as e:
            logger.error(f"❌ Collection metadata processing failed: {e}")
            return {
                "collection_id": collection_id,
                "operation_id": operation_id,
                "status": "failed",
                "error": str(e),
                "processing_time": time.time() - start_time,
            }

    async def import_collection_from_directory(
        self,
        collection_id: str,
        source_directory: str,
        file_patterns: List[str] = None,
        recursive: bool = True,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Import an entire collection from a directory"""

        if collection_id not in self.active_collections:
            raise ValueError(f"Collection {collection_id} not found")

        operation_id = f"{collection_id}_import_{int(time.time())}"
        start_time = time.time()

        try:
            logger.info(f"📥 Starting collection import from {source_directory}")

            # Use bulk processor for collection import
            progress = await self.bulk_processor.bulk_collection_import(
                source_directory=source_directory,
                operation_id=operation_id,
                file_patterns=file_patterns,
                progress_callback=progress_callback,
            )

            processing_time = time.time() - start_time

            # Update collection with discovered files
            collection = self.active_collections[collection_id]
            collection.total_items += progress.successful_items
            collection.last_modified = time.time()

            result = {
                "collection_id": collection_id,
                "operation_id": operation_id,
                "status": progress.status.value,
                "imported_files": progress.successful_items,
                "failed_files": progress.failed_items,
                "total_files_found": progress.total_items,
                "processing_time": processing_time,
                "source_directory": source_directory,
            }

            logger.info(f"✅ Collection import completed: {result}")
            return result

        except Exception as e:
            logger.error(f"❌ Collection import failed: {e}")
            return {
                "collection_id": collection_id,
                "operation_id": operation_id,
                "status": "failed",
                "error": str(e),
                "processing_time": time.time() - start_time,
            }

    async def export_collection_metadata(
        self,
        collection_id: str,
        export_format: str = "json",
        include_file_paths: bool = True,
    ) -> Dict[str, Any]:
        """Export collection metadata in various formats"""

        if collection_id not in self.active_collections:
            raise ValueError(f"Collection {collection_id} not found")

        collection = self.active_collections[collection_id]

        try:
            # Prepare export data
            export_data = {
                "collection_metadata": collection.to_dict(),
                "export_timestamp": time.time(),
                "export_format": export_format,
            }

            # Add cached processing results if available
            if self.config.enable_caching:
                cached_result = await self.redis_manager.get(
                    f"collection:{collection_id}:processing_result"
                )
                if cached_result:
                    export_data["processing_results"] = json.loads(cached_result)

            # Format-specific processing
            if export_format.lower() == "json":
                formatted_data = json.dumps(export_data, indent=2)
            elif export_format.lower() == "csv":
                # Placeholder for CSV format
                formatted_data = "CSV format not yet implemented"
            else:
                raise ValueError(f"Unsupported export format: {export_format}")

            result = {
                "collection_id": collection_id,
                "export_format": export_format,
                "data_size_bytes": len(formatted_data.encode("utf-8")),
                "exported_data": formatted_data,
            }

            logger.info(
                f"📤 Collection metadata exported: {collection_id} ({export_format})"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Collection export failed: {e}")
            return {"collection_id": collection_id, "status": "failed", "error": str(e)}

    async def cleanup_collection(
        self,
        collection_id: str,
        cleanup_rules: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Perform cleanup operations on a collection"""

        if collection_id not in self.active_collections:
            raise ValueError(f"Collection {collection_id} not found")

        operation_id = f"{collection_id}_cleanup_{int(time.time())}"

        try:
            # Use bulk processor for cleanup operations
            progress = await self.bulk_processor.bulk_cleanup_operation(
                target_directory=cleanup_rules.get("target_directory", ""),
                operation_id=operation_id,
                cleanup_rules=cleanup_rules,
                progress_callback=progress_callback,
            )

            result = {
                "collection_id": collection_id,
                "operation_id": operation_id,
                "status": progress.status.value,
                "cleaned_items": progress.successful_items,
                "failed_items": progress.failed_items,
                "cleanup_rules": cleanup_rules,
            }

            logger.info(f"✅ Collection cleanup completed: {result}")
            return result

        except Exception as e:
            logger.error(f"❌ Collection cleanup failed: {e}")
            return {
                "collection_id": collection_id,
                "operation_id": operation_id,
                "status": "failed",
                "error": str(e),
            }

    async def get_collection_statistics(self, collection_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a collection"""

        if collection_id not in self.active_collections:
            raise ValueError(f"Collection {collection_id} not found")

        collection = self.active_collections[collection_id]

        # Check cache first
        cache_key = f"collection:{collection_id}:statistics"
        if self.config.enable_caching:
            cached_stats = await self.redis_manager.get(cache_key)
            if cached_stats:
                self.processing_stats["cache_hit_ratio"] += 1
                return json.loads(cached_stats)

        try:
            stats = {
                "collection_metadata": collection.to_dict(),
                "file_size_mb": collection.total_size_bytes / (1024 * 1024),
                "average_file_size_mb": (
                    collection.total_size_bytes / collection.total_items / (1024 * 1024)
                    if collection.total_items > 0
                    else 0
                ),
                "collection_age_days": (time.time() - collection.created_at)
                / (24 * 3600),
                "last_modified_days_ago": (time.time() - collection.last_modified)
                / (24 * 3600),
            }

            # Cache statistics
            if self.config.enable_caching:
                await self.redis_manager.set(
                    cache_key, json.dumps(stats), ttl=self.config.cache_ttl_seconds
                )

            return stats

        except Exception as e:
            logger.error(f"❌ Failed to get collection statistics: {e}")
            return {"error": str(e)}

    def get_processing_statistics(self) -> Dict[str, Any]:
        """Get overall processing statistics"""
        return {
            "processing_stats": self.processing_stats,
            "active_collections": len(self.active_collections),
            "queue_sizes": {
                priority.value: len(queue)
                for priority, queue in self.processing_queues.items()
            },
            "config": self.config.to_dict(),
        }

    async def optimize_collection_storage(self, collection_id: str) -> Dict[str, Any]:
        """Optimize storage for a collection"""
        # Placeholder for storage optimization logic
        # This could include deduplication, compression, format conversion, etc.

        logger.info(f"🔧 Optimizing storage for collection {collection_id}")

        return {
            "collection_id": collection_id,
            "optimization_status": "completed",
            "space_saved_bytes": 0,  # Placeholder
            "optimization_methods_applied": ["placeholder"],
        }


# Convenience functions
async def create_media_collection(
    collection_id: str,
    name: str,
    collection_type: CollectionType,
    description: str = "",
    config: Optional[CollectionProcessingConfig] = None,
) -> MediaCollectionManager:
    """Create a new media collection with manager"""
    manager = MediaCollectionManager(config)
    await manager.create_collection(collection_id, name, collection_type, description)
    return manager


async def process_directory_as_collection(
    source_directory: str,
    collection_name: str,
    collection_type: CollectionType = CollectionType.MIXED_COLLECTION,
    file_patterns: List[str] = None,
    config: Optional[CollectionProcessingConfig] = None,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Process an entire directory as a media collection"""

    collection_id = f"dir_{hashlib.md5(source_directory.encode(), usedforsecurity=False).hexdigest()[:8]}"

    manager = MediaCollectionManager(config)

    # Create collection
    await manager.create_collection(
        collection_id=collection_id,
        name=collection_name,
        collection_type=collection_type,
        description=f"Collection imported from {source_directory}",
    )

    # Import from directory
    import_result = await manager.import_collection_from_directory(
        collection_id=collection_id,
        source_directory=source_directory,
        file_patterns=file_patterns,
        progress_callback=progress_callback,
    )

    return {
        "collection_id": collection_id,
        "manager": manager,
        "import_result": import_result,
    }
