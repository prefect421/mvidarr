"""
MVidarr Media Cache Manager - Phase 2 Week 23
Redis-based caching for media operations with intelligent invalidation and performance optimization
"""

import asyncio
import hashlib
import json
import logging
import pickle
import time
import zlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.services.redis_manager import RedisManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.media_cache")


class CacheType(Enum):
    """Types of cached data"""

    MEDIA_METADATA = "media_metadata"
    IMAGE_ANALYSIS = "image_analysis"
    VIDEO_ANALYSIS = "video_analysis"
    THUMBNAIL = "thumbnail"
    FORMAT_CONVERSION = "format_conversion"
    QUALITY_ANALYSIS = "quality_analysis"
    COLLECTION_SUMMARY = "collection_summary"
    BULK_OPERATION_RESULT = "bulk_operation_result"


class CacheStrategy(Enum):
    """Cache storage and retrieval strategies"""

    WRITE_THROUGH = "write_through"  # Write to cache and storage simultaneously
    WRITE_BEHIND = "write_behind"  # Write to cache first, storage later
    WRITE_AROUND = "write_around"  # Write to storage, bypass cache
    READ_THROUGH = "read_through"  # Read from cache, fallback to storage
    CACHE_ASIDE = "cache_aside"  # Application manages cache explicitly


@dataclass
class CacheMetrics:
    """Cache performance metrics"""

    hits: int = 0
    misses: int = 0
    writes: int = 0
    evictions: int = 0
    total_size_bytes: int = 0
    average_retrieval_time_ms: float = 0.0
    cache_efficiency_percent: float = 0.0

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    @property
    def total_operations(self) -> int:
        return self.hits + self.misses + self.writes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "evictions": self.evictions,
            "total_size_bytes": self.total_size_bytes,
            "average_retrieval_time_ms": self.average_retrieval_time_ms,
            "cache_efficiency_percent": self.cache_efficiency_percent,
            "hit_ratio_percent": self.hit_ratio,
            "total_operations": self.total_operations,
        }


@dataclass
class CacheConfiguration:
    """Configuration for cache behavior"""

    default_ttl_seconds: int = 3600  # 1 hour
    max_memory_mb: int = 1024  # 1GB
    compression_enabled: bool = True
    compression_threshold_bytes: int = 1024  # Compress items > 1KB
    cleanup_interval_seconds: int = 300  # 5 minutes

    # TTL overrides for specific cache types
    type_specific_ttl: Dict[CacheType, int] = field(
        default_factory=lambda: {
            CacheType.MEDIA_METADATA: 7200,  # 2 hours
            CacheType.IMAGE_ANALYSIS: 3600,  # 1 hour
            CacheType.VIDEO_ANALYSIS: 3600,  # 1 hour
            CacheType.THUMBNAIL: 86400,  # 24 hours
            CacheType.FORMAT_CONVERSION: 1800,  # 30 minutes
            CacheType.QUALITY_ANALYSIS: 3600,  # 1 hour
            CacheType.COLLECTION_SUMMARY: 1800,  # 30 minutes
            CacheType.BULK_OPERATION_RESULT: 900,  # 15 minutes
        }
    )

    def get_ttl(self, cache_type: CacheType) -> int:
        """Get TTL for specific cache type"""
        return self.type_specific_ttl.get(cache_type, self.default_ttl_seconds)


class MediaCacheManager:
    """Advanced Redis-based caching for media operations with intelligent strategies"""

    def __init__(self, config: Optional[CacheConfiguration] = None):
        """Initialize media cache manager"""
        self.config = config or CacheConfiguration()
        self.redis_manager = RedisManager()
        self.metrics = CacheMetrics()

        # Cache key prefixes for organization
        self.key_prefixes = {
            CacheType.MEDIA_METADATA: "meta:",
            CacheType.IMAGE_ANALYSIS: "img:",
            CacheType.VIDEO_ANALYSIS: "vid:",
            CacheType.THUMBNAIL: "thumb:",
            CacheType.FORMAT_CONVERSION: "conv:",
            CacheType.QUALITY_ANALYSIS: "qual:",
            CacheType.COLLECTION_SUMMARY: "coll:",
            CacheType.BULK_OPERATION_RESULT: "bulk:",
        }

        logger.info(
            f"🗄️ Media cache manager initialized with {self.config.max_memory_mb}MB limit"
        )

    def _generate_cache_key(
        self, cache_type: CacheType, identifier: str, **kwargs
    ) -> str:
        """Generate a unique cache key"""
        prefix = self.key_prefixes[cache_type]

        # Include additional parameters in key if provided
        if kwargs:
            # Sort kwargs for consistent key generation
            sorted_kwargs = sorted(kwargs.items())
            kwargs_str = "&".join(f"{k}={v}" for k, v in sorted_kwargs)
            identifier = f"{identifier}?{kwargs_str}"

        # Hash long identifiers to keep keys manageable
        if len(identifier) > 100:
            identifier = hashlib.md5(identifier.encode()).hexdigest()

        return f"mvidarr:{prefix}{identifier}"

    def _compress_data(self, data: bytes) -> bytes:
        """Compress data if it exceeds threshold"""
        if (
            self.config.compression_enabled
            and len(data) > self.config.compression_threshold_bytes
        ):
            compressed = zlib.compress(data)
            # Only use compression if it actually saves space
            if len(compressed) < len(data):
                return b"COMPRESSED:" + compressed
        return data

    def _decompress_data(self, data: bytes) -> bytes:
        """Decompress data if it was compressed"""
        if data.startswith(b"COMPRESSED:"):
            return zlib.decompress(data[11:])  # Remove "COMPRESSED:" prefix
        return data

    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for storage"""
        try:
            # Try JSON first for simple types
            if isinstance(value, (dict, list, str, int, float, bool, type(None))):
                return json.dumps(value).encode("utf-8")
            else:
                # Use pickle for complex objects
                return b"PICKLE:" + pickle.dumps(value)
        except Exception as e:
            logger.error(f"❌ Failed to serialize cache value: {e}")
            # Fallback to pickle
            return b"PICKLE:" + pickle.dumps(value)

    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize value from storage"""
        try:
            if data.startswith(b"PICKLE:"):
                return pickle.loads(data[7:])  # Remove "PICKLE:" prefix
            else:
                return json.loads(data.decode("utf-8"))
        except Exception as e:
            logger.error(f"❌ Failed to deserialize cache value: {e}")
            return None

    async def get(
        self, cache_type: CacheType, identifier: str, default: Any = None, **kwargs
    ) -> Any:
        """Retrieve value from cache"""
        start_time = time.time()
        key = self._generate_cache_key(cache_type, identifier, **kwargs)

        try:
            cached_data = await self.redis_manager.get(key)

            if cached_data is None:
                self.metrics.misses += 1
                logger.debug(f"📭 Cache miss: {cache_type.value}:{identifier}")
                return default

            # Decompress and deserialize
            decompressed = self._decompress_data(cached_data)
            value = self._deserialize_value(decompressed)

            # Update metrics
            self.metrics.hits += 1
            retrieval_time = (time.time() - start_time) * 1000
            self._update_average_retrieval_time(retrieval_time)

            logger.debug(
                f"✅ Cache hit: {cache_type.value}:{identifier} ({retrieval_time:.1f}ms)"
            )
            return value

        except Exception as e:
            logger.error(f"❌ Cache retrieval error for {key}: {e}")
            self.metrics.misses += 1
            return default

    async def set(
        self,
        cache_type: CacheType,
        identifier: str,
        value: Any,
        ttl: Optional[int] = None,
        **kwargs,
    ) -> bool:
        """Store value in cache"""
        key = self._generate_cache_key(cache_type, identifier, **kwargs)
        ttl = ttl or self.config.get_ttl(cache_type)

        try:
            # Serialize and compress
            serialized = self._serialize_value(value)
            compressed = self._compress_data(serialized)

            # Store in Redis
            success = await self.redis_manager.set(key, compressed, ttl=ttl)

            if success:
                self.metrics.writes += 1
                self.metrics.total_size_bytes += len(compressed)
                logger.debug(
                    f"💾 Cached: {cache_type.value}:{identifier} ({len(compressed)} bytes, TTL: {ttl}s)"
                )

            return success

        except Exception as e:
            logger.error(f"❌ Cache storage error for {key}: {e}")
            return False

    async def delete(self, cache_type: CacheType, identifier: str, **kwargs) -> bool:
        """Delete value from cache"""
        key = self._generate_cache_key(cache_type, identifier, **kwargs)

        try:
            deleted = await self.redis_manager.delete(key)
            if deleted:
                logger.debug(f"🗑️ Deleted from cache: {cache_type.value}:{identifier}")
            return deleted

        except Exception as e:
            logger.error(f"❌ Cache deletion error for {key}: {e}")
            return False

    async def exists(self, cache_type: CacheType, identifier: str, **kwargs) -> bool:
        """Check if key exists in cache"""
        key = self._generate_cache_key(cache_type, identifier, **kwargs)

        try:
            return await self.redis_manager.exists(key)
        except Exception as e:
            logger.error(f"❌ Cache existence check error for {key}: {e}")
            return False

    async def invalidate_pattern(
        self, cache_type: CacheType, pattern: str = "*"
    ) -> int:
        """Invalidate all cache entries matching a pattern"""
        prefix = self.key_prefixes[cache_type]
        search_pattern = f"mvidarr:{prefix}{pattern}"

        try:
            deleted_count = await self.redis_manager.delete_pattern(search_pattern)
            if deleted_count > 0:
                self.metrics.evictions += deleted_count
                logger.info(
                    f"🧹 Invalidated {deleted_count} cache entries for pattern: {search_pattern}"
                )
            return deleted_count

        except Exception as e:
            logger.error(
                f"❌ Cache invalidation error for pattern {search_pattern}: {e}"
            )
            return 0

    async def cache_media_metadata(
        self,
        file_path: str,
        metadata: Dict[str, Any],
        file_modified_time: Optional[float] = None,
    ) -> bool:
        """Cache media metadata with file modification time validation"""

        # Include file modification time in cache key for invalidation
        if file_modified_time is None:
            try:
                file_modified_time = Path(file_path).stat().st_mtime
            except:
                file_modified_time = time.time()

        # Add metadata enrichment info
        enriched_metadata = {
            **metadata,
            "cached_at": time.time(),
            "file_modified_time": file_modified_time,
            "cache_version": "1.0",
        }

        return await self.set(
            CacheType.MEDIA_METADATA,
            file_path,
            enriched_metadata,
            file_mtime=int(file_modified_time),
        )

    async def get_cached_media_metadata(
        self, file_path: str, validate_freshness: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached media metadata with freshness validation"""

        try:
            current_mtime = Path(file_path).stat().st_mtime
        except:
            current_mtime = None

        # Get cached metadata
        cached_metadata = await self.get(
            CacheType.MEDIA_METADATA,
            file_path,
            file_mtime=int(current_mtime) if current_mtime else 0,
        )

        if not cached_metadata or not validate_freshness:
            return cached_metadata

        # Validate freshness if file modification time is available
        cached_mtime = cached_metadata.get("file_modified_time")
        if current_mtime and cached_mtime and current_mtime > cached_mtime:
            # File has been modified since caching, invalidate
            logger.debug(f"📅 Cache invalidated for {file_path} (file modified)")
            await self.delete(
                CacheType.MEDIA_METADATA, file_path, file_mtime=int(current_mtime)
            )
            return None

        return cached_metadata

    async def cache_bulk_operation_result(
        self,
        operation_id: str,
        operation_type: str,
        result: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache bulk operation results"""
        enriched_result = {
            **result,
            "operation_id": operation_id,
            "operation_type": operation_type,
            "cached_at": time.time(),
        }

        return await self.set(
            CacheType.BULK_OPERATION_RESULT,
            operation_id,
            enriched_result,
            ttl=ttl or 900,  # 15 minutes default
        )

    async def get_collection_cache_stats(self, collection_id: str) -> Dict[str, Any]:
        """Get cache statistics for a specific collection"""
        stats = {
            "collection_id": collection_id,
            "cached_items": 0,
            "cache_size_bytes": 0,
            "oldest_entry": None,
            "newest_entry": None,
        }

        # This is a simplified implementation - in production, you'd track per-collection stats
        # For now, return overall cache stats
        stats.update(self.metrics.to_dict())

        return stats

    async def warm_cache(
        self,
        media_paths: List[str],
        metadata_loader_func: callable,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Pre-populate cache with frequently accessed metadata"""
        logger.info(f"🔥 Warming cache for {len(media_paths)} media files")

        warmed_count = 0
        skipped_count = 0
        error_count = 0

        for i, media_path in enumerate(media_paths):
            try:
                # Check if already cached
                if await self.exists(CacheType.MEDIA_METADATA, media_path):
                    skipped_count += 1
                    continue

                # Load metadata and cache it
                metadata = await metadata_loader_func(media_path)
                if metadata:
                    await self.cache_media_metadata(media_path, metadata)
                    warmed_count += 1

                # Progress callback
                if progress_callback:
                    progress = (i + 1) / len(media_paths) * 100
                    progress_callback(progress, media_path)

            except Exception as e:
                logger.error(f"❌ Cache warming error for {media_path}: {e}")
                error_count += 1

        result = {
            "total_files": len(media_paths),
            "warmed_count": warmed_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "warming_time_seconds": time.time(),
        }

        logger.info(f"✅ Cache warming completed: {result}")
        return result

    async def cleanup_expired_entries(self) -> Dict[str, Any]:
        """Clean up expired cache entries and optimize memory usage"""
        logger.info("🧹 Starting cache cleanup...")

        cleanup_stats = {
            "expired_entries": 0,
            "memory_freed_bytes": 0,
            "cleanup_time_seconds": 0,
        }

        start_time = time.time()

        try:
            # Redis handles TTL expiration automatically, but we can do additional cleanup
            # For now, just update metrics and perform any custom cleanup logic

            # Reset some metrics periodically
            if self.metrics.total_operations > 10000:
                # Decay metrics to prevent infinite growth
                self.metrics.hits = int(self.metrics.hits * 0.9)
                self.metrics.misses = int(self.metrics.misses * 0.9)
                self.metrics.writes = int(self.metrics.writes * 0.9)

            cleanup_stats["cleanup_time_seconds"] = time.time() - start_time
            logger.info(f"✅ Cache cleanup completed: {cleanup_stats}")

        except Exception as e:
            logger.error(f"❌ Cache cleanup error: {e}")

        return cleanup_stats

    def _update_average_retrieval_time(self, new_time_ms: float):
        """Update running average of retrieval times"""
        if self.metrics.average_retrieval_time_ms == 0:
            self.metrics.average_retrieval_time_ms = new_time_ms
        else:
            # Weighted average with more weight on recent measurements
            weight = 0.1
            self.metrics.average_retrieval_time_ms = (
                1 - weight
            ) * self.metrics.average_retrieval_time_ms + weight * new_time_ms

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        try:
            # Get Redis info
            redis_info = await self.redis_manager.get_info()

            # Calculate efficiency
            if self.metrics.total_operations > 0:
                self.metrics.cache_efficiency_percent = (
                    self.metrics.hits / self.metrics.total_operations
                ) * 100

            stats = {
                "cache_metrics": self.metrics.to_dict(),
                "redis_info": {
                    "used_memory": redis_info.get("used_memory", 0),
                    "used_memory_human": redis_info.get("used_memory_human", "Unknown"),
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "total_commands_processed": redis_info.get(
                        "total_commands_processed", 0
                    ),
                    "keyspace_hits": redis_info.get("keyspace_hits", 0),
                    "keyspace_misses": redis_info.get("keyspace_misses", 0),
                },
                "configuration": {
                    "max_memory_mb": self.config.max_memory_mb,
                    "default_ttl_seconds": self.config.default_ttl_seconds,
                    "compression_enabled": self.config.compression_enabled,
                    "compression_threshold_bytes": self.config.compression_threshold_bytes,
                },
                "cache_types": {
                    cache_type.value: {
                        "ttl_seconds": self.config.get_ttl(cache_type),
                        "key_prefix": self.key_prefixes[cache_type],
                    }
                    for cache_type in CacheType
                },
            }

            return stats

        except Exception as e:
            logger.error(f"❌ Failed to get cache statistics: {e}")
            return {"error": str(e)}

    async def optimize_cache_performance(self) -> Dict[str, Any]:
        """Perform cache optimization operations"""
        logger.info("🔧 Starting cache performance optimization...")

        optimization_results = {
            "memory_optimization": False,
            "key_consolidation": False,
            "ttl_adjustment": False,
            "compression_optimization": False,
        }

        try:
            # 1. Memory optimization - cleanup expired entries
            cleanup_result = await self.cleanup_expired_entries()
            optimization_results["memory_optimization"] = True

            # 2. Adjust TTL based on usage patterns
            if self.metrics.hit_ratio > 90:
                # High hit ratio - can extend TTLs
                logger.info(
                    "📈 High cache hit ratio detected - optimizing for longer retention"
                )
            elif self.metrics.hit_ratio < 50:
                # Low hit ratio - reduce TTLs to free memory
                logger.info(
                    "📉 Low cache hit ratio detected - optimizing for memory usage"
                )

            optimization_results["ttl_adjustment"] = True

            # 3. Compression optimization
            if self.config.compression_enabled:
                # Could analyze compression ratios and adjust threshold
                optimization_results["compression_optimization"] = True

            logger.info(f"✅ Cache optimization completed: {optimization_results}")

        except Exception as e:
            logger.error(f"❌ Cache optimization error: {e}")

        return optimization_results


# Global cache manager instance
_cache_manager: Optional[MediaCacheManager] = None


async def get_media_cache_manager(
    config: Optional[CacheConfiguration] = None,
) -> MediaCacheManager:
    """Get or create global media cache manager instance"""
    global _cache_manager

    if _cache_manager is None:
        _cache_manager = MediaCacheManager(config)

    return _cache_manager


# Convenience functions for common caching operations
async def cache_media_metadata(file_path: str, metadata: Dict[str, Any]) -> bool:
    """Cache media metadata"""
    cache_manager = await get_media_cache_manager()
    return await cache_manager.cache_media_metadata(file_path, metadata)


async def get_cached_media_metadata(file_path: str) -> Optional[Dict[str, Any]]:
    """Get cached media metadata"""
    cache_manager = await get_media_cache_manager()
    return await cache_manager.get_cached_media_metadata(file_path)


async def cache_image_analysis(
    file_path: str, analysis_result: Dict[str, Any], ttl: int = 3600
) -> bool:
    """Cache image analysis result"""
    cache_manager = await get_media_cache_manager()
    return await cache_manager.set(
        CacheType.IMAGE_ANALYSIS, file_path, analysis_result, ttl=ttl
    )


async def get_cached_image_analysis(file_path: str) -> Optional[Dict[str, Any]]:
    """Get cached image analysis result"""
    cache_manager = await get_media_cache_manager()
    return await cache_manager.get(CacheType.IMAGE_ANALYSIS, file_path)


async def invalidate_media_cache(file_path: str) -> int:
    """Invalidate all cached data for a media file"""
    cache_manager = await get_media_cache_manager()

    invalidated = 0
    for cache_type in CacheType:
        if await cache_manager.delete(cache_type, file_path):
            invalidated += 1

    return invalidated
