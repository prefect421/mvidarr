"""
Redis-based API Response Caching Middleware - Phase 3 Week 33
FastAPI middleware for intelligent response caching and performance optimization
"""

import asyncio
import hashlib
import json
import time
from typing import Any, Callable, Dict, List, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.cache")


class APIResponseCacheMiddleware(BaseHTTPMiddleware):
    """Middleware for intelligent Redis-based API response caching"""

    def __init__(
        self,
        app,
        cache_ttl: int = 300,  # 5 minutes default
        cache_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_cache_size: int = 1000,
    ):
        super().__init__(app)
        self.cache_ttl = cache_ttl
        self.cache_patterns = cache_patterns or [
            "/api/videos",
            "/api/artists",
            "/api/playlists",
            "/api/settings",
            "/health",
        ]
        self.exclude_patterns = exclude_patterns or [
            "/api/auth",
            "/api/admin/users",
            "/api/demo",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        self.max_cache_size = max_cache_size
        self.cache_manager = None
        logger.info(f"🚀 API Response Cache middleware initialized (TTL: {cache_ttl}s)")

    async def get_cache_manager(self) -> MediaCacheManager:
        """Get or create cache manager instance"""
        if not self.cache_manager:
            self.cache_manager = MediaCacheManager()
        return self.cache_manager

    def _should_cache_request(self, request: Request) -> bool:
        """Determine if request should be cached"""
        path = request.url.path
        method = request.method

        # Only cache GET requests
        if method != "GET":
            return False

        # Check exclusion patterns first
        for pattern in self.exclude_patterns:
            if pattern in path:
                return False

        # Check inclusion patterns
        for pattern in self.cache_patterns:
            if pattern in path:
                return True

        return False

    def _generate_cache_key(self, request: Request) -> str:
        """Generate a unique cache key for the request"""
        # Include method, path, query params, and user context
        key_components = [
            request.method,
            request.url.path,
            str(sorted(request.query_params.items())),
        ]

        # Add user context if available (for user-specific caching)
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            key_components.append(f"user:{user_id}")

        key_string = "|".join(key_components)
        return f"api_cache:{hashlib.md5(key_string.encode(), usedforsecurity=False).hexdigest()}"

    async def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached response if available"""
        try:
            cache_manager = await self.get_cache_manager()
            cached_data = await cache_manager.get(cache_key)

            if cached_data:
                logger.debug(f"📦 Cache HIT for key: {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")

        return None

    async def _store_cached_response(
        self, cache_key: str, response_data: Dict[str, Any]
    ) -> bool:
        """Store response in cache"""
        try:
            cache_manager = await self.get_cache_manager()

            # Add cache metadata
            cache_entry = {
                "data": response_data,
                "cached_at": time.time(),
                "ttl": self.cache_ttl,
            }

            await cache_manager.set(
                cache_key, json.dumps(cache_entry), ttl=self.cache_ttl
            )

            logger.debug(f"💾 Cached response for key: {cache_key}")
            return True

        except Exception as e:
            logger.error(f"Cache storage error: {e}")
            return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with caching logic"""
        # Check if this request should be cached
        if not self._should_cache_request(request):
            return await call_next(request)

        cache_key = self._generate_cache_key(request)

        # Try to get cached response
        cached_response = await self._get_cached_response(cache_key)
        if cached_response:
            response_data = cached_response.get("data", {})

            # Create response from cached data
            response = Response(
                content=json.dumps(response_data.get("content")),
                status_code=response_data.get("status_code", 200),
                headers=response_data.get("headers", {}),
                media_type=response_data.get("media_type", "application/json"),
            )

            # Add cache headers
            response.headers["X-Cache-Status"] = "HIT"
            response.headers["X-Cache-Key"] = cache_key[:16] + "..."
            response.headers["X-Cached-At"] = str(
                int(cached_response.get("cached_at", 0))
            )

            return response

        # Process request normally
        start_time = time.time()
        response = await call_next(request)
        processing_time = time.time() - start_time

        # Cache successful responses (200-299)
        if 200 <= response.status_code < 300:
            try:
                # Read response content
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk

                # Prepare response data for caching
                response_data = {
                    "content": response_body.decode("utf-8"),
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "media_type": response.media_type,
                }

                # Store in cache (async, don't wait)
                asyncio.create_task(
                    self._store_cached_response(cache_key, response_data)
                )

                # Create new response with the same content
                new_response = Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=response.headers,
                    media_type=response.media_type,
                )

                # Add cache headers
                new_response.headers["X-Cache-Status"] = "MISS"
                new_response.headers["X-Cache-Key"] = cache_key[:16] + "..."
                new_response.headers["X-Processing-Time"] = f"{processing_time:.3f}s"

                return new_response

            except Exception as e:
                logger.error(f"Error preparing response for cache: {e}")

        return response


class CacheInvalidationMiddleware(BaseHTTPMiddleware):
    """Middleware to invalidate cache on data-modifying requests"""

    def __init__(self, app):
        super().__init__(app)
        self.cache_manager = None
        self.invalidation_patterns = {
            "/api/videos": ["api_cache:*videos*", "api_cache:*playlists*"],
            "/api/artists": ["api_cache:*artists*", "api_cache:*videos*"],
            "/api/playlists": ["api_cache:*playlists*"],
            "/api/settings": ["api_cache:*settings*", "api_cache:*health*"],
        }

    async def get_cache_manager(self) -> MediaCacheManager:
        """Get or create cache manager instance"""
        if not self.cache_manager:
            self.cache_manager = MediaCacheManager()
        return self.cache_manager

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and invalidate cache if needed"""
        path = request.url.path
        method = request.method

        # Process the request
        response = await call_next(request)

        # Invalidate cache for data-modifying operations
        if (
            method in ["POST", "PUT", "PATCH", "DELETE"]
            and 200 <= response.status_code < 300
        ):
            await self._invalidate_related_cache(path)

        return response

    async def _invalidate_related_cache(self, path: str):
        """Invalidate cache patterns related to the modified path"""
        try:
            cache_manager = await self.get_cache_manager()

            for pattern, cache_keys in self.invalidation_patterns.items():
                if pattern in path:
                    for cache_pattern in cache_keys:
                        # Use cache manager's pattern-based invalidation
                        invalidated = await cache_manager.invalidate_pattern(
                            cache_pattern
                        )
                        if invalidated:
                            logger.info(f"🗑️ Invalidated cache pattern: {cache_pattern}")
                    break

        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")


# Cache decorator for individual functions
def cache_response(ttl: int = 300, key_prefix: str = "func_cache"):
    """Decorator for caching function responses"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_parts = [key_prefix, func.__name__]

            # Add non-self arguments to cache key
            for arg in args[1:]:  # Skip 'self' argument
                if isinstance(arg, (str, int, float, bool)):
                    key_parts.append(str(arg))

            for k, v in kwargs.items():
                if isinstance(v, (str, int, float, bool)):
                    key_parts.append(f"{k}:{v}")

            cache_key = ":".join(key_parts)
            cache_key_hash = hashlib.md5(cache_key.encode(), usedforsecurity=False).hexdigest()
            final_key = f"func_cache:{cache_key_hash}"

            # Try to get from cache
            try:
                cache_manager = MediaCacheManager()
                cached = await cache_manager.get(final_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Function cache retrieval error: {e}")

            # Execute function and cache result
            result = await func(*args, **kwargs)

            try:
                await cache_manager.set(
                    final_key, json.dumps(result, default=str), ttl=ttl
                )
            except Exception as e:
                logger.warning(f"Function cache storage error: {e}")

            return result

        return wrapper

    return decorator
