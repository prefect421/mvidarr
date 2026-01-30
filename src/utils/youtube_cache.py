"""
YouTube API Response Caching Utility

This module provides in-memory caching for YouTube API responses to reduce
quota usage by avoiding redundant API calls for the same data.

Caching Strategy:
- Search results: 3 hours TTL (searches don't change often)
- Playlist contents: 1 hour TTL (playlists update more frequently)
- Video details: 24 hours TTL (video metadata is mostly static)
- Channel info: 7 days TTL (channel info rarely changes)

Issue: Addresses quota exhaustion by caching API responses
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class YouTubeCache:
    """In-memory cache for YouTube API responses with TTL support"""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._hit_count = 0
        self._miss_count = 0

        # TTL configuration (in seconds)
        self.ttl_search = 3 * 3600  # 3 hours
        self.ttl_playlist = 1 * 3600  # 1 hour
        self.ttl_video_details = 24 * 3600  # 24 hours
        self.ttl_channel = 7 * 24 * 3600  # 7 days
        self.ttl_default = 1 * 3600  # 1 hour default

    def _generate_key(self, operation: str, params: Dict[str, Any]) -> str:
        """Generate a unique cache key from operation and parameters"""
        # Sort params for consistent hashing
        sorted_params = json.dumps(params, sort_keys=True)
        key_str = f"{operation}:{sorted_params}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _is_expired(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if a cache entry has expired"""
        return time.time() > cache_entry["expires_at"]

    def _cleanup_expired(self):
        """Remove expired entries from cache"""
        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if current_time > entry["expires_at"]
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def get(
        self, operation: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached data if available and not expired

        Args:
            operation: Type of API operation (search, playlist, video_details, channel)
            params: Parameters used in the API call

        Returns:
            Cached data if available and valid, None otherwise
        """
        cache_key = self._generate_key(operation, params)

        if cache_key in self._cache:
            entry = self._cache[cache_key]

            if not self._is_expired(entry):
                self._hit_count += 1
                logger.debug(
                    f"Cache HIT for {operation} (hits: {self._hit_count}, "
                    f"misses: {self._miss_count}, "
                    f"hit rate: {self.get_hit_rate():.1%})"
                )
                return entry["data"]
            else:
                # Remove expired entry
                del self._cache[cache_key]
                logger.debug(f"Cache entry expired for {operation}")

        self._miss_count += 1
        logger.debug(
            f"Cache MISS for {operation} (hits: {self._hit_count}, "
            f"misses: {self._miss_count}, "
            f"hit rate: {self.get_hit_rate():.1%})"
        )
        return None

    def set(
        self, operation: str, params: Dict[str, Any], data: Dict[str, Any], ttl: Optional[int] = None
    ):
        """
        Store data in cache with appropriate TTL

        Args:
            operation: Type of API operation
            params: Parameters used in the API call
            data: Response data to cache
            ttl: Optional custom TTL in seconds (overrides operation-based TTL)
        """
        # Determine TTL based on operation type
        if ttl is None:
            if operation == "search":
                ttl = self.ttl_search
            elif operation == "playlist":
                ttl = self.ttl_playlist
            elif operation == "video_details":
                ttl = self.ttl_video_details
            elif operation == "channel":
                ttl = self.ttl_channel
            else:
                ttl = self.ttl_default

        cache_key = self._generate_key(operation, params)
        expires_at = time.time() + ttl

        self._cache[cache_key] = {
            "data": data,
            "expires_at": expires_at,
            "operation": operation,
            "cached_at": time.time(),
        }

        logger.debug(
            f"Cached {operation} data (TTL: {ttl}s, total entries: {len(self._cache)})"
        )

        # Periodic cleanup of expired entries
        if len(self._cache) % 100 == 0:
            self._cleanup_expired()

    def invalidate(self, operation: Optional[str] = None, params: Optional[Dict[str, Any]] = None):
        """
        Invalidate cache entries

        Args:
            operation: If provided, only invalidate entries for this operation
            params: If provided with operation, invalidate specific entry
        """
        if operation and params:
            # Invalidate specific entry
            cache_key = self._generate_key(operation, params)
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.info(f"Invalidated cache entry for {operation}")
        elif operation:
            # Invalidate all entries for this operation
            keys_to_delete = [
                key
                for key, entry in self._cache.items()
                if entry["operation"] == operation
            ]
            for key in keys_to_delete:
                del self._cache[key]
            logger.info(f"Invalidated {len(keys_to_delete)} cache entries for {operation}")
        else:
            # Clear entire cache
            count = len(self._cache)
            self._cache.clear()
            self._hit_count = 0
            self._miss_count = 0
            logger.info(f"Cleared entire cache ({count} entries)")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        current_time = time.time()
        active_entries = sum(
            1 for entry in self._cache.values() if current_time <= entry["expires_at"]
        )
        expired_entries = len(self._cache) - active_entries

        return {
            "total_entries": len(self._cache),
            "active_entries": active_entries,
            "expired_entries": expired_entries,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": self.get_hit_rate(),
            "total_requests": self._hit_count + self._miss_count,
        }

    def get_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self._hit_count + self._miss_count
        return (self._hit_count / total) if total > 0 else 0.0

    def cleanup(self):
        """Manually trigger cleanup of expired entries"""
        self._cleanup_expired()


# Global cache instance
_youtube_cache = None


def get_youtube_cache() -> YouTubeCache:
    """Get or create the global YouTube cache instance"""
    global _youtube_cache
    if _youtube_cache is None:
        _youtube_cache = YouTubeCache()
        logger.info("Initialized YouTube API response cache")
    return _youtube_cache


def clear_youtube_cache():
    """Clear the global cache (useful for testing)"""
    global _youtube_cache
    if _youtube_cache:
        _youtube_cache.invalidate()
