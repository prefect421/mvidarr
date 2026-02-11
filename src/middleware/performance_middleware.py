"""
MVidarr Performance Middleware - Phase 2 Week 24
FastAPI middleware for automatic API performance tracking and monitoring
"""

import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.services.performance_monitor import (
    get_performance_monitor,
    track_api_response_time,
    track_error_rate,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.performance")


class PerformanceTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically track API endpoint performance"""

    def __init__(self, app, exclude_paths: Optional[list] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/static",
            "/css",
        ]
        logger.info(
            f"📊 Performance tracking middleware initialized, excluding: {self.exclude_paths}"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Track performance metrics for each API request"""
        start_time = time.time()
        path = request.url.path
        method = request.method

        # Skip tracking for excluded paths
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)

        # Track concurrent requests
        monitor = await get_performance_monitor()
        await monitor.record_concurrent_operations("api_requests", 1)

        try:
            # Process the request
            response = await call_next(request)

            # Calculate response time
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            status_code = response.status_code

            # Track the API performance
            endpoint = f"{method} {path}"
            await track_api_response_time(endpoint, response_time, status_code)

            # Log slow requests (>1 second)
            if response_time > 1000:
                logger.warning(
                    f"🐌 Slow API response: {endpoint} took {response_time:.1f}ms (status: {status_code})"
                )

            # Add performance headers to response
            response.headers["X-Response-Time"] = f"{response_time:.2f}ms"
            response.headers["X-Processed-At"] = str(int(time.time()))

            return response

        except Exception as e:
            # Track error
            response_time = (time.time() - start_time) * 1000
            endpoint = f"{method} {path}"
            await track_api_response_time(endpoint, response_time, 500)

            # Track error rate
            await track_error_rate("api_requests", 1, 1)  # 1 error out of 1 request

            logger.error(
                f"❌ API request failed: {endpoint} after {response_time:.1f}ms - {e}"
            )
            raise

        finally:
            # Decrement concurrent request counter
            await monitor.record_concurrent_operations("api_requests", -1)


class CacheHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add cache-related headers to API responses"""

    def __init__(self, app, default_cache_ttl: int = 300):
        super().__init__(app)
        self.default_cache_ttl = default_cache_ttl
        logger.info(
            f"🗄️ Cache headers middleware initialized with {default_cache_ttl}s default TTL"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add appropriate cache headers based on endpoint"""
        response = await call_next(request)
        path = request.url.path

        # Cache control for different endpoint types
        if path.startswith("/api/system-health/metrics/"):
            # Short cache for metrics (30 seconds)
            response.headers["Cache-Control"] = "public, max-age=30"
            response.headers["X-Cache-Strategy"] = "short-term"

        elif path.startswith("/api/system-health/"):
            # Very short cache for health endpoints (10 seconds)
            response.headers["Cache-Control"] = "public, max-age=10"
            response.headers["X-Cache-Strategy"] = "real-time"

        elif path.startswith("/api/image-processing/") or path.startswith(
            "/api/advanced-image-processing/"
        ):
            # Longer cache for processed images metadata (1 hour)
            response.headers["Cache-Control"] = "public, max-age=3600"
            response.headers["X-Cache-Strategy"] = "long-term"

        elif path.startswith("/api/bulk-operations/"):
            # No cache for bulk operations (dynamic content)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["X-Cache-Strategy"] = "no-cache"

        else:
            # Default cache behavior
            response.headers[
                "Cache-Control"
            ] = f"public, max-age={self.default_cache_ttl}"
            response.headers["X-Cache-Strategy"] = "default"

        # Add cache timestamp
        response.headers["X-Cache-Timestamp"] = str(int(time.time()))

        return response


class ResourceMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware to monitor resource usage during API requests"""

    def __init__(self, app, track_memory: bool = True):
        super().__init__(app)
        self.track_memory = track_memory
        logger.info(
            f"📈 Resource monitoring middleware initialized (memory tracking: {track_memory})"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Monitor resource usage during request processing"""
        path = request.url.path

        # Skip resource monitoring for static files and docs
        skip_paths = ["/static", "/css", "/docs", "/redoc", "/openapi.json"]
        if any(path.startswith(skip) for skip in skip_paths):
            return await call_next(request)

        start_time = time.time()

        # Get initial memory usage if tracking enabled
        initial_memory = None
        if self.track_memory:
            try:
                import psutil

                process = psutil.Process()
                initial_memory = process.memory_info().rss
            except Exception:
                pass

        try:
            # Process the request
            response = await call_next(request)

            # Calculate resource usage
            processing_time = time.time() - start_time

            if self.track_memory and initial_memory:
                try:
                    final_memory = process.memory_info().rss
                    memory_delta = final_memory - initial_memory

                    # Add memory usage headers
                    response.headers["X-Memory-Delta"] = f"{memory_delta}"
                    response.headers["X-Memory-Final"] = f"{final_memory}"

                    # Log significant memory increases (>50MB)
                    if memory_delta > 50 * 1024 * 1024:
                        logger.warning(
                            f"🧠 High memory usage: {path} used {memory_delta / (1024*1024):.1f}MB"
                        )

                except Exception:
                    pass

            # Add timing headers
            response.headers["X-Processing-Time"] = f"{processing_time:.6f}s"

            return response

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                f"❌ Resource monitoring error for {path}: {e} (after {processing_time:.3f}s)"
            )
            raise
