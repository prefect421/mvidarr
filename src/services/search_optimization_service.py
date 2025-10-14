"""
Search optimization service for MVidarr
Provides caching and query optimization for search operations
"""

import hashlib
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.search_optimization")


class SearchCache:
    """In-memory cache for search results with TTL"""

    def __init__(self, default_ttl: int = 300):  # 5 minutes default TTL
        self.cache: Dict[str, tuple] = {}
        self.default_ttl = default_ttl

    def _generate_cache_key(self, query_params: Dict[str, Any]) -> str:
        """Generate a cache key from query parameters"""
        # Sort parameters for consistent hashing
        sorted_params = sorted(query_params.items())
        cache_string = str(sorted_params)
        return hashlib.md5(cache_string.encode()).hexdigest()

    def get(self, query_params: Dict[str, Any]) -> Optional[Any]:
        """Get cached result if available and not expired"""
        cache_key = self._generate_cache_key(query_params)

        if cache_key in self.cache:
            result, timestamp, ttl = self.cache[cache_key]
            if time.time() - timestamp < ttl:
                logger.debug(f"Cache hit for key: {cache_key}")
                return result
            else:
                # Remove expired entry
                del self.cache[cache_key]
                logger.debug(f"Cache expired for key: {cache_key}")

        return None

    def set(
        self, query_params: Dict[str, Any], result: Any, ttl: Optional[int] = None
    ) -> None:
        """Store result in cache with TTL"""
        cache_key = self._generate_cache_key(query_params)
        ttl = ttl or self.default_ttl

        self.cache[cache_key] = (result, time.time(), ttl)
        logger.debug(f"Cached result for key: {cache_key}, TTL: {ttl}s")

    def invalidate_pattern(self, pattern: str) -> None:
        """Invalidate cache entries matching a pattern"""
        keys_to_remove = []
        for key in self.cache.keys():
            if pattern in key:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.cache[key]
            logger.debug(f"Invalidated cache key: {key}")

    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
        logger.info("Search cache cleared")

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        current_time = time.time()
        active_entries = 0
        expired_entries = 0

        for result, timestamp, ttl in self.cache.values():
            if current_time - timestamp < ttl:
                active_entries += 1
            else:
                expired_entries += 1

        return {
            "total_entries": len(self.cache),
            "active_entries": active_entries,
            "expired_entries": expired_entries,
            "hit_rate": getattr(self, "_hit_count", 0)
            / max(getattr(self, "_access_count", 1), 1)
            * 100,
        }


class SearchOptimizationService:
    """Service for optimizing search operations"""

    def __init__(self):
        self.cache = SearchCache()
        self._hit_count = 0
        self._access_count = 0

    def optimize_database_indexes(self) -> bool:
        """Create additional composite indexes for better search performance"""
        try:
            with get_db() as session:
                # Create composite indexes for common search patterns
                indexes = [
                    # Artist search optimizations
                    "CREATE INDEX IF NOT EXISTS idx_artist_search_composite ON artists(name, monitored, created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_artist_name_status ON artists(name, auto_download, monitored)",
                    "CREATE INDEX IF NOT EXISTS idx_artist_metadata ON artists(imvdb_id, spotify_id, source)",
                    # Video search optimizations
                    "CREATE INDEX IF NOT EXISTS idx_video_search_composite ON videos(title, artist_id, status, year)",
                    "CREATE INDEX IF NOT EXISTS idx_video_metadata ON videos(duration, view_count, like_count, year)",
                    "CREATE INDEX IF NOT EXISTS idx_video_search_text ON videos(title, description) WHERE description IS NOT NULL",
                    "CREATE INDEX IF NOT EXISTS idx_video_artist_status ON videos(artist_id, status, created_at)",
                    # Download history optimizations
                    "CREATE INDEX IF NOT EXISTS idx_download_composite ON downloads(artist_id, status, created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_download_status_date ON downloads(status, created_at, video_id)",
                ]

                for index_sql in indexes:
                    try:
                        session.execute(text(index_sql))
                        logger.info(
                            f"Created index: {index_sql.split('ON')[0].split('IF NOT EXISTS')[1].strip()}"
                        )
                    except Exception as e:
                        logger.warning(f"Index creation failed or already exists: {e}")

                session.commit()
                logger.info("Database indexes optimized successfully")
                return True

        except Exception as e:
            logger.error(f"Failed to optimize database indexes: {e}")
            return False

    def cached_artist_search(self, query_params: Dict[str, Any], search_func) -> Any:
        """Cache wrapper for artist search operations"""
        self._access_count += 1

        # Check cache first
        cached_result = self.cache.get(query_params)
        if cached_result is not None:
            self._hit_count += 1
            return cached_result

        # Execute search function
        result = search_func(query_params)

        # Cache the result (shorter TTL for frequently changing data)
        ttl = (
            180 if query_params.get("search") else 300
        )  # 3 min for search, 5 min for lists
        self.cache.set(query_params, result, ttl)

        return result

    def cached_video_search(self, query_params: Dict[str, Any], search_func) -> Any:
        """Cache wrapper for video search operations"""
        self._access_count += 1

        # Check cache first
        cached_result = self.cache.get(query_params)
        if cached_result is not None:
            self._hit_count += 1
            return cached_result

        # Execute search function
        result = search_func(query_params)

        # Cache the result
        ttl = 240  # 4 minutes for video searches
        self.cache.set(query_params, result, ttl)

        return result

    def invalidate_artist_cache(self, artist_id: Optional[int] = None) -> None:
        """Invalidate cache entries related to artists"""
        if artist_id:
            self.cache.invalidate_pattern(f"artist_id_{artist_id}")
        else:
            self.cache.invalidate_pattern("artist")

        logger.info(f"Invalidated artist cache for ID: {artist_id}")

    def invalidate_video_cache(
        self, video_id: Optional[int] = None, artist_id: Optional[int] = None
    ) -> None:
        """Invalidate cache entries related to videos"""
        if video_id:
            self.cache.invalidate_pattern(f"video_id_{video_id}")
        if artist_id:
            self.cache.invalidate_pattern(f"artist_id_{artist_id}")

        self.cache.invalidate_pattern("video")
        logger.info(
            f"Invalidated video cache for video ID: {video_id}, artist ID: {artist_id}"
        )

    def get_optimized_query_hints(self, query_type: str) -> List[str]:
        """Get database-specific query hints for optimization"""
        hints = []

        if query_type == "artist_search":
            hints = [
                "USE INDEX (idx_artist_search_composite)",
                "STRAIGHT_JOIN",  # For MariaDB query optimization
            ]
        elif query_type == "video_search":
            hints = ["USE INDEX (idx_video_search_composite)", "STRAIGHT_JOIN"]
        elif query_type == "complex_join":
            hints = ["USE INDEX (idx_video_artist_status, idx_artist_search_composite)"]

        return hints

    def analyze_query_performance(self, query_sql: str) -> Dict[str, Any]:
        """Analyze query performance using EXPLAIN"""
        try:
            with get_db() as session:
                # Get query execution plan
                explain_result = session.execute(
                    text(f"EXPLAIN {query_sql}")
                ).fetchall()

                analysis = {
                    "query": query_sql,
                    "execution_plan": [],
                    "recommendations": [],
                }

                for row in explain_result:
                    plan_step = {
                        "table": row[2] if len(row) > 2 else None,
                        "type": row[3] if len(row) > 3 else None,
                        "possible_keys": row[4] if len(row) > 4 else None,
                        "key": row[5] if len(row) > 5 else None,
                        "rows": row[8] if len(row) > 8 else None,
                        "extra": row[9] if len(row) > 9 else None,
                    }
                    analysis["execution_plan"].append(plan_step)

                    # Add recommendations based on execution plan
                    if plan_step["type"] == "ALL":
                        analysis["recommendations"].append(
                            f"Consider adding index for table {plan_step['table']}"
                        )
                    if plan_step["rows"] and int(plan_step["rows"]) > 1000:
                        analysis["recommendations"].append(
                            f"High row count ({plan_step['rows']}) for table {plan_step['table']}"
                        )

                return analysis

        except Exception as e:
            logger.error(f"Query analysis failed: {e}")
            return {"error": str(e)}

    def cleanup_cache(self) -> None:
        """Clean up expired cache entries"""
        current_time = time.time()
        keys_to_remove = []

        for key, (result, timestamp, ttl) in self.cache.cache.items():
            if current_time - timestamp >= ttl:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.cache.cache[key]

        logger.info(f"Cleaned up {len(keys_to_remove)} expired cache entries")

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        cache_stats = self.cache.stats()

        return {
            "cache_stats": cache_stats,
            "hit_rate": self._hit_count / max(self._access_count, 1) * 100,
            "total_requests": self._access_count,
            "cache_hits": self._hit_count,
            "cache_misses": self._access_count - self._hit_count,
            "optimization_enabled": True,
        }


# Global instance
search_optimization_service = SearchOptimizationService()
