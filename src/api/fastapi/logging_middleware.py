"""
FastAPI Logging Middleware for Request Tracking and Correlation IDs
Production-ready request logging with structured output
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware

from src.utils.structured_logger import (
    CorrelationContext,
    get_structured_logger,
    set_correlation_id,
    set_user_context,
)

logger = get_structured_logger("mvidarr.api.middleware")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic request logging with correlation tracking"""

    def __init__(self, app, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/api/health",
            "/static",
            "/favicon.ico",
            "/metrics",
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # Generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        # Extract user information from session if available
        user_id = None
        try:
            if hasattr(request, "session") and request.session:
                user_info = request.session.get("user", {})
                if isinstance(user_info, dict):
                    user_id = str(user_info.get("user_id", ""))
        except Exception:
            pass  # Session might not be available

        # Set up correlation context
        start_time = time.time()

        with CorrelationContext(
            correlation_id=correlation_id, user_id=user_id, request_id=request_id
        ):
            # Log incoming request
            logger.info(
                f"Incoming request: {request.method} {request.url.path}",
                method=request.method,
                path=request.url.path,
                query_params=(
                    str(request.query_params) if request.query_params else None
                ),
                client_ip=self._get_client_ip(request),
                user_agent=request.headers.get("User-Agent"),
                content_type=request.headers.get("Content-Type"),
                content_length=request.headers.get("Content-Length"),
                referer=request.headers.get("Referer"),
                event_type="request_start",
            )

            # Process request
            try:
                response = await call_next(request)

                # Calculate duration
                duration = time.time() - start_time

                # Log response
                logger.api_request(
                    method=request.method,
                    endpoint=request.url.path,
                    status_code=response.status_code,
                    duration=duration,
                    client_ip=self._get_client_ip(request),
                    user_agent=request.headers.get("User-Agent"),
                    response_size=response.headers.get("Content-Length"),
                    cache_status=response.headers.get("X-Cache-Status"),
                )

                # Add correlation ID to response headers
                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Request-ID"] = request_id

                # Log slow requests as warnings
                if duration > 5.0:  # 5 seconds threshold
                    logger.warning(
                        f"Slow request detected: {request.method} {request.url.path}",
                        duration_ms=round(duration * 1000, 2),
                        event_type="slow_request",
                    )

                return response

            except Exception as e:
                duration = time.time() - start_time

                # Log request failure
                logger.error(
                    f"Request failed: {request.method} {request.url.path}",
                    method=request.method,
                    path=request.url.path,
                    duration=duration,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    client_ip=self._get_client_ip(request),
                    event_type="request_error",
                )

                raise  # Re-raise the exception

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        # Check for forwarded headers (common in production behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to direct client IP
        return getattr(request.client, "host", "unknown")


class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """Middleware for security event logging"""

    def __init__(self, app):
        super().__init__(app)
        self.security_logger = get_structured_logger("mvidarr.security")
        self.sensitive_endpoints = [
            "/auth/login",
            "/auth/logout",
            "/auth/register",
            "/auth/oauth",
            "/api/admin",
            "/api/settings",
            "/api/users",
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if this is a security-sensitive endpoint
        is_sensitive = any(
            request.url.path.startswith(endpoint)
            for endpoint in self.sensitive_endpoints
        )

        if not is_sensitive:
            return await call_next(request)

        # Log security event
        start_time = time.time()
        client_ip = self._get_client_ip(request)

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Log successful security event
            self.security_logger.audit(
                "endpoint_access",
                endpoint=request.url.path,
                method=request.method,
                client_ip=client_ip,
                user_agent=request.headers.get("User-Agent"),
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
                success=200 <= response.status_code < 400,
            )

            return response

        except Exception as e:
            duration = time.time() - start_time

            # Log failed security event
            self.security_logger.audit(
                "endpoint_access_failed",
                endpoint=request.url.path,
                method=request.method,
                client_ip=client_ip,
                user_agent=request.headers.get("User-Agent"),
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=round(duration * 1000, 2),
                success=False,
            )

            raise

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return getattr(request.client, "host", "unknown")


class PerformanceLoggingRoute(APIRoute):
    """Custom route for performance tracking"""

    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            start_time = time.time()

            try:
                response = await original_route_handler(request)
                duration = time.time() - start_time

                # Log performance metrics for API endpoints
                if request.url.path.startswith("/api/"):
                    perf_logger = get_structured_logger("mvidarr.performance")
                    perf_logger.performance(
                        operation=f"{request.method} {request.url.path}",
                        duration=duration,
                        endpoint=request.url.path,
                        method=request.method,
                        status_code=response.status_code,
                    )

                return response

            except Exception as e:
                duration = time.time() - start_time

                # Log failed operations
                perf_logger = get_structured_logger("mvidarr.performance")
                perf_logger.error(
                    f"Operation failed: {request.method} {request.url.path}",
                    operation=f"{request.method} {request.url.path}",
                    duration=duration,
                    endpoint=request.url.path,
                    method=request.method,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

                raise

        return custom_route_handler


def setup_logging_middleware(app):
    """Setup all logging middleware for the FastAPI app"""

    # Add request logging middleware
    app.add_middleware(
        RequestLoggingMiddleware,
        exclude_paths=[
            "/health",
            "/api/health",
            "/static",
            "/favicon.ico",
            "/docs",
            "/redoc",
            "/openapi.json",
        ],
    )

    # Add security audit middleware
    app.add_middleware(SecurityAuditMiddleware)

    # Set custom route class for performance logging
    app.router.route_class = PerformanceLoggingRoute

    logger.info("Logging middleware configured successfully")

    return app
