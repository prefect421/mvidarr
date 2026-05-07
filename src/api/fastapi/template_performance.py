"""
Template Performance Optimization - Issue 130 Template System Migration
Advanced performance optimization for FastAPI template rendering
"""

import asyncio
import gzip
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from fastapi import Request, Response
from fastapi.responses import HTMLResponse

from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.template_performance")


@dataclass
class TemplateMetrics:
    """Template performance metrics"""

    template_name: str
    render_time_ms: float
    cache_hit: bool
    content_length: int
    compression_ratio: float
    context_size: int
    timestamp: datetime


class TemplateCache:
    """Advanced template caching system"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_stats = {"hits": 0, "misses": 0, "memory_hits": 0, "redis_hits": 0}
        self.max_memory_items = 100
        self.default_ttl = 3600  # 1 hour

    async def initialize(self):
        """Initialize cache with Redis client"""
        if not self.redis_client:
            try:
                self.redis_client = await get_redis_client()
                logger.info("Template cache initialized with Redis")
            except Exception as e:
                logger.warning(f"Redis not available for template cache: {e}")

    def _generate_cache_key(self, template_name: str, context_hash: str) -> str:
        """Generate cache key for template and context"""
        return f"template_cache:{template_name}:{context_hash}"

    def _hash_context(self, context: Dict[str, Any]) -> str:
        """Generate hash of template context"""
        try:
            # Remove non-serializable items
            serializable_context = {}
            for key, value in context.items():
                try:
                    json.dumps(value, default=str)
                    serializable_context[key] = value
                except (TypeError, ValueError):
                    serializable_context[key] = str(type(value))

            context_str = json.dumps(serializable_context, sort_keys=True, default=str)
            return hashlib.sha256(context_str.encode()).hexdigest()[:16]

        except Exception as e:
            logger.warning(f"Error hashing context: {e}")
            return hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]

    async def get(self, template_name: str, context: Dict[str, Any]) -> Optional[str]:
        """Get cached template content"""
        context_hash = self._hash_context(context)
        cache_key = self._generate_cache_key(template_name, context_hash)

        # Check memory cache first
        if cache_key in self.memory_cache:
            cached_item = self.memory_cache[cache_key]
            if cached_item["expires_at"] > datetime.utcnow():
                self.cache_stats["hits"] += 1
                self.cache_stats["memory_hits"] += 1
                return cached_item["content"]
            else:
                del self.memory_cache[cache_key]

        # Check Redis cache
        if self.redis_client:
            try:
                cached_content = await self.redis_client.get(cache_key)
                if cached_content:
                    # Store in memory cache for faster access
                    self._store_in_memory(cache_key, cached_content.decode("utf-8"))
                    self.cache_stats["hits"] += 1
                    self.cache_stats["redis_hits"] += 1
                    return cached_content.decode("utf-8")
            except Exception as e:
                logger.warning(f"Redis cache get error: {e}")

        self.cache_stats["misses"] += 1
        return None

    async def set(
        self,
        template_name: str,
        context: Dict[str, Any],
        content: str,
        ttl: Optional[int] = None,
    ):
        """Cache template content"""
        context_hash = self._hash_context(context)
        cache_key = self._generate_cache_key(template_name, context_hash)
        ttl = ttl or self.default_ttl

        # Store in memory cache
        self._store_in_memory(cache_key, content, ttl)

        # Store in Redis cache
        if self.redis_client:
            try:
                await self.redis_client.setex(cache_key, ttl, content.encode("utf-8"))
            except Exception as e:
                logger.warning(f"Redis cache set error: {e}")

    def _store_in_memory(self, cache_key: str, content: str, ttl: Optional[int] = None):
        """Store content in memory cache"""
        # Implement LRU eviction if needed
        if len(self.memory_cache) >= self.max_memory_items:
            # Remove oldest item
            oldest_key = min(
                self.memory_cache.keys(),
                key=lambda k: self.memory_cache[k]["stored_at"],
            )
            del self.memory_cache[oldest_key]

        self.memory_cache[cache_key] = {
            "content": content,
            "stored_at": datetime.utcnow(),
            "expires_at": datetime.utcnow()
            + timedelta(seconds=ttl or self.default_ttl),
        }

    async def invalidate(self, template_name: str = None, pattern: str = None):
        """Invalidate cached templates"""
        if template_name:
            # Invalidate all cached versions of a specific template
            keys_to_remove = [
                key
                for key in self.memory_cache.keys()
                if key.startswith(f"template_cache:{template_name}:")
            ]

            for key in keys_to_remove:
                del self.memory_cache[key]

            if self.redis_client:
                try:
                    redis_pattern = f"template_cache:{template_name}:*"
                    keys = await self.redis_client.keys(redis_pattern)
                    if keys:
                        await self.redis_client.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis cache invalidation error: {e}")

        elif pattern:
            # Invalidate by pattern
            keys_to_remove = [key for key in self.memory_cache.keys() if pattern in key]

            for key in keys_to_remove:
                del self.memory_cache[key]

            if self.redis_client:
                try:
                    keys = await self.redis_client.keys(f"*{pattern}*")
                    if keys:
                        await self.redis_client.delete(*keys)
                except Exception as e:
                    logger.warning(f"Redis pattern invalidation error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / max(total_requests, 1)) * 100

        return {
            "total_requests": total_requests,
            "cache_hits": self.cache_stats["hits"],
            "cache_misses": self.cache_stats["misses"],
            "hit_rate": hit_rate,
            "memory_hits": self.cache_stats["memory_hits"],
            "redis_hits": self.cache_stats["redis_hits"],
            "memory_cache_size": len(self.memory_cache),
        }


class TemplateCompressor:
    """Template content compression system"""

    @staticmethod
    def compress_html(content: str) -> bytes:
        """Compress HTML content using gzip"""
        return gzip.compress(content.encode("utf-8"))

    @staticmethod
    def decompress_html(compressed_content: bytes) -> str:
        """Decompress HTML content"""
        return gzip.decompress(compressed_content).decode("utf-8")

    @staticmethod
    def minify_html(content: str) -> str:
        """Basic HTML minification"""
        import re

        # Remove comments
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)

        # Remove extra whitespace
        content = re.sub(r"\s+", " ", content)

        # Remove whitespace around tags
        content = re.sub(r">\s+<", "><", content)

        return content.strip()

    @staticmethod
    def should_compress(content: str, min_size: int = 1000) -> bool:
        """Determine if content should be compressed"""
        return len(content) >= min_size


class PerformanceOptimizedRenderer:
    """High-performance template renderer with caching and optimization"""

    def __init__(
        self,
        template_system,
        cache_enabled: bool = True,
        compression_enabled: bool = True,
    ):
        self.template_system = template_system
        self.cache_enabled = cache_enabled
        self.compression_enabled = compression_enabled
        self.cache = TemplateCache()
        self.metrics: List[TemplateMetrics] = []
        self.optimization_hooks: List[Callable] = []

    async def initialize(self):
        """Initialize performance optimizer"""
        if self.cache_enabled:
            await self.cache.initialize()

        logger.info("Performance optimized renderer initialized")

    def add_optimization_hook(self, hook: Callable):
        """Add custom optimization hook"""
        self.optimization_hooks.append(hook)

    async def render_template_optimized(
        self, template_name: str, request: Request, context: Dict[str, Any] = None
    ) -> HTMLResponse:
        """Render template with performance optimizations"""
        start_time = time.time()
        cache_hit = False

        try:
            # Build full context
            full_context = await self.template_system.get_template_context(
                request, context
            )

            # Check cache first
            cached_content = None
            if self.cache_enabled:
                cached_content = await self.cache.get(template_name, full_context)
                if cached_content:
                    cache_hit = True

            if not cached_content:
                # Apply optimization hooks
                for hook in self.optimization_hooks:
                    try:
                        if asyncio.iscoroutinefunction(hook):
                            full_context = (
                                await hook(template_name, full_context) or full_context
                            )
                        else:
                            full_context = (
                                hook(template_name, full_context) or full_context
                            )
                    except Exception as e:
                        logger.warning(f"Optimization hook error: {e}")

                # Render template
                rendered_content = await self.template_system.render_template(
                    template_name, request, full_context
                )

                # Apply minification
                if self.compression_enabled:
                    rendered_content = TemplateCompressor.minify_html(rendered_content)

                # Cache the result
                if self.cache_enabled:
                    await self.cache.set(template_name, full_context, rendered_content)

                cached_content = rendered_content

            # Create response
            response = HTMLResponse(content=cached_content)

            # Add performance headers
            render_time = (time.time() - start_time) * 1000
            response.headers["X-Render-Time"] = f"{render_time:.2f}ms"
            response.headers["X-Cache-Hit"] = "true" if cache_hit else "false"

            # Compression
            if self.compression_enabled and TemplateCompressor.should_compress(
                cached_content
            ):
                if "gzip" in request.headers.get("accept-encoding", ""):
                    compressed_content = TemplateCompressor.compress_html(
                        cached_content
                    )
                    response = Response(
                        content=compressed_content,
                        media_type="text/html",
                        headers={
                            "Content-Encoding": "gzip",
                            "X-Render-Time": f"{render_time:.2f}ms",
                            "X-Cache-Hit": "true" if cache_hit else "false",
                            "X-Compressed": "true",
                        },
                    )

            # Record metrics
            self._record_metrics(
                template_name, render_time, cache_hit, len(cached_content), full_context
            )

            return response

        except Exception as e:
            logger.error(f"Optimized template rendering error for {template_name}: {e}")
            # Fallback to non-optimized rendering
            return await self.template_system.render_response(
                template_name, request, context
            )

    def _record_metrics(
        self,
        template_name: str,
        render_time: float,
        cache_hit: bool,
        content_length: int,
        context: Dict[str, Any],
    ):
        """Record template rendering metrics"""
        try:
            metrics = TemplateMetrics(
                template_name=template_name,
                render_time_ms=render_time,
                cache_hit=cache_hit,
                content_length=content_length,
                compression_ratio=1.0,  # Would be calculated for compressed content
                context_size=len(str(context)),
                timestamp=datetime.utcnow(),
            )

            self.metrics.append(metrics)

            # Keep only recent metrics (last 1000)
            if len(self.metrics) > 1000:
                self.metrics = self.metrics[-1000:]

        except Exception as e:
            logger.warning(f"Error recording metrics: {e}")

    async def preload_templates(
        self, template_names: List[str], sample_context: Dict[str, Any] = None
    ):
        """Preload and cache commonly used templates"""
        if not self.cache_enabled:
            return

        logger.info(f"Preloading {len(template_names)} templates")

        sample_context = sample_context or {}

        for template_name in template_names:
            try:
                # Create a minimal request for context generation
                from fastapi import Request
                from starlette.datastructures import URL, Headers

                scope = {
                    "type": "http",
                    "method": "GET",
                    "path": "/",
                    "query_string": b"",
                    "headers": [(b"host", b"localhost")],
                }
                request = Request(scope)

                # Render and cache
                await self.render_template_optimized(
                    template_name, request, sample_context
                )

            except Exception as e:
                logger.warning(f"Error preloading template {template_name}: {e}")

    async def warm_cache(self):
        """Warm up cache with commonly used templates"""
        common_templates = [
            "base.html",
            "index.html",
            "videos.html",
            "artists.html",
            "playlists.html",
        ]

        await self.preload_templates(common_templates)

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        if not self.metrics:
            return {"no_metrics": "No templates rendered yet"}

        # Calculate statistics
        render_times = [m.render_time_ms for m in self.metrics]
        cache_hits = sum(1 for m in self.metrics if m.cache_hit)

        return {
            "total_renders": len(self.metrics),
            "cache_hit_rate": (cache_hits / len(self.metrics)) * 100,
            "avg_render_time_ms": sum(render_times) / len(render_times),
            "min_render_time_ms": min(render_times),
            "max_render_time_ms": max(render_times),
            "cache_stats": self.cache.get_stats() if self.cache_enabled else None,
            "recent_templates": [m.template_name for m in self.metrics[-10:]],
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def invalidate_cache(self, template_name: str = None):
        """Invalidate template cache"""
        if self.cache_enabled:
            await self.cache.invalidate(template_name)


# Template optimization middleware
class TemplateOptimizationMiddleware:
    """Middleware for template optimization"""

    def __init__(self, app, renderer: PerformanceOptimizedRenderer):
        self.app = app
        self.renderer = renderer

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)

            # Check if this is a template request
            path = request.url.path

            # Template routes (customize based on your routing)
            template_routes = {
                "/": "index.html",
                "/videos": "videos.html",
                "/artists": "artists.html",
                "/playlists": "playlists.html",
                "/settings": "settings.html",
            }

            if path in template_routes:
                try:
                    response = await self.renderer.render_template_optimized(
                        template_routes[path], request
                    )
                    await response(scope, receive, send)
                    return
                except Exception as e:
                    logger.error(f"Template optimization middleware error: {e}")
                    # Fall through to normal handling

        await self.app(scope, receive, send)


# Utility functions
async def create_optimized_renderer(
    template_system, cache_enabled: bool = True, compression_enabled: bool = True
) -> PerformanceOptimizedRenderer:
    """Create and initialize optimized renderer"""
    renderer = PerformanceOptimizedRenderer(
        template_system, cache_enabled, compression_enabled
    )
    await renderer.initialize()
    return renderer


def add_context_optimization_hook(renderer: PerformanceOptimizedRenderer):
    """Add context optimization hook"""

    def optimize_context(template_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # Remove large objects that aren't needed for this template
        if template_name == "index.html":
            # Dashboard doesn't need full video list
            context.pop("full_video_list", None)
        elif template_name == "videos.html":
            # Videos page doesn't need full artist list
            context.pop("full_artist_list", None)

        return context

    renderer.add_optimization_hook(optimize_context)


def add_static_content_hook(renderer: PerformanceOptimizedRenderer):
    """Add static content optimization hook"""

    async def optimize_static_content(
        template_name: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Add versioned static file URLs for better caching
        context["static_version"] = int(time.time())  # Simple versioning

        # Preload critical resources
        context["preload_resources"] = ["/static/css/main.css", "/static/js/core.js"]

        return context

    renderer.add_optimization_hook(optimize_static_content)


# Global performance optimized renderer instance
_optimized_renderer = None


async def get_optimized_renderer(template_system) -> PerformanceOptimizedRenderer:
    """Get global optimized renderer instance"""
    global _optimized_renderer

    if _optimized_renderer is None:
        _optimized_renderer = await create_optimized_renderer(template_system)

        # Add default optimization hooks
        add_context_optimization_hook(_optimized_renderer)
        add_static_content_hook(_optimized_renderer)

        # Warm up cache
        await _optimized_renderer.warm_cache()

    return _optimized_renderer
