"""
Request/Response Logging System - Issue 128 Advanced FastAPI Features
Comprehensive API usage logging with performance metrics and audit trails
"""

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import FastAPI, Request, Response
from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = get_logger("mvidarr.api.logging")


class LogLevel(Enum):
    """API logging levels"""

    NONE = "none"  # No logging
    BASIC = "basic"  # Basic request/response info
    DETAILED = "detailed"  # Includes headers and timing
    FULL = "full"  # Includes request/response bodies
    DEBUG = "debug"  # Maximum detail for debugging


class LogFormat(Enum):
    """Log output formats"""

    JSON = "json"
    TEXT = "text"
    STRUCTURED = "structured"


@dataclass
class APILogEntry:
    """API request/response log entry"""

    request_id: str
    timestamp: str
    method: str
    path: str
    query_params: Dict[str, Any]
    headers: Dict[str, str]
    client_ip: str
    user_agent: str
    api_version: str
    user_id: Optional[str]

    # Request data
    request_size: int
    request_body: Optional[str]

    # Response data
    status_code: int
    response_size: int
    response_body: Optional[str]
    response_headers: Dict[str, str]

    # Performance metrics
    processing_time_ms: float
    database_time_ms: Optional[float]
    cache_time_ms: Optional[float]

    # Additional context
    endpoint_name: Optional[str]
    errors: List[str]
    warnings: List[str]
    tags: List[str]


class RequestResponseLogger:
    """Comprehensive request/response logging system"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None

        # Logging configuration
        self.log_level = LogLevel(self.config.get("log_level", "detailed"))
        self.log_format = LogFormat(self.config.get("log_format", "json"))
        self.log_file_path = self.config.get(
            "log_file", "/var/log/mvidarr/api_requests.log"
        )
        self.max_body_size = self.config.get("max_body_size", 10000)  # 10KB

        # Performance tracking
        self.enable_performance_tracking = self.config.get("enable_performance", True)
        self.track_database_queries = self.config.get("track_db_queries", True)
        self.track_cache_operations = self.config.get("track_cache", True)

        # Filtering and sampling
        self.excluded_paths = set(
            self.config.get(
                "excluded_paths", ["/health", "/metrics", "/favicon.ico", "/static"]
            )
        )
        self.sampling_rate = self.config.get(
            "sampling_rate", 1.0
        )  # Log 100% by default

        # Storage settings
        self.store_in_redis = self.config.get("store_in_redis", True)
        self.redis_retention_hours = self.config.get("redis_retention", 24)
        self.store_in_file = self.config.get("store_in_file", True)

        # Active requests tracking
        self.active_requests: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        """Initialize logging system"""
        try:
            if self.store_in_redis:
                self.redis_client = await get_redis_client()

            logger.info(
                f"API request logging initialized - Level: {self.log_level.value}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize request logging: {e}")
            raise

    def generate_request_id(self) -> str:
        """Generate unique request ID"""
        return f"req_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    def should_log_request(self, request: Request) -> bool:
        """Determine if request should be logged"""
        # Check excluded paths
        path = request.url.path
        if any(excluded in path for excluded in self.excluded_paths):
            return False

        # Check sampling rate
        if self.sampling_rate < 1.0:
            import random

            return random.random() < self.sampling_rate

        return True

    async def extract_request_data(self, request: Request) -> Dict[str, Any]:
        """Extract relevant data from request"""
        request_data = {
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": self._sanitize_headers(dict(request.headers)),
            "client_ip": self._get_client_ip(request),
            "user_agent": request.headers.get("User-Agent", ""),
            "api_version": getattr(request.state, "api_version", "unknown"),
            "user_id": self._extract_user_id(request),
            "content_length": request.headers.get("Content-Length", "0"),
        }

        # Extract request body if needed and size allows
        if self.log_level in [LogLevel.FULL, LogLevel.DEBUG]:
            try:
                content_length = int(request_data["content_length"])
                if content_length <= self.max_body_size and content_length > 0:
                    body = await request.body()
                    if body:
                        try:
                            # Try to parse as JSON for better logging
                            request_data["body"] = json.loads(body.decode("utf-8"))
                        except:
                            request_data["body"] = body.decode("utf-8", errors="ignore")
            except Exception as e:
                logger.warning(f"Failed to extract request body: {e}")

        return request_data

    def extract_response_data(self, response: Response) -> Dict[str, Any]:
        """Extract relevant data from response"""
        response_data = {
            "status_code": response.status_code,
            "headers": self._sanitize_headers(dict(response.headers)),
            "content_length": response.headers.get("Content-Length", "0"),
        }

        # Extract response body if needed and possible
        if self.log_level in [LogLevel.FULL, LogLevel.DEBUG]:
            # Note: Response body extraction is complex with FastAPI streaming
            # This is a simplified version
            if hasattr(response, "body") and response.body:
                try:
                    content_length = int(response_data["content_length"])
                    if content_length <= self.max_body_size:
                        body_content = response.body
                        if isinstance(body_content, bytes):
                            body_content = body_content.decode("utf-8", errors="ignore")
                        response_data["body"] = body_content
                except Exception as e:
                    logger.warning(f"Failed to extract response body: {e}")

        return response_data

    async def create_log_entry(
        self,
        request_id: str,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
        processing_time: float,
        additional_metrics: Optional[Dict[str, Any]] = None,
    ) -> APILogEntry:
        """Create comprehensive log entry"""

        log_entry = APILogEntry(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            method=request_data["method"],
            path=request_data["path"],
            query_params=request_data["query_params"],
            headers=request_data["headers"] if self.log_level != LogLevel.BASIC else {},
            client_ip=request_data["client_ip"],
            user_agent=request_data["user_agent"],
            api_version=request_data["api_version"],
            user_id=request_data.get("user_id"),
            request_size=int(request_data.get("content_length", 0)),
            request_body=(
                request_data.get("body") if self.log_level == LogLevel.FULL else None
            ),
            status_code=response_data["status_code"],
            response_size=int(response_data.get("content_length", 0)),
            response_body=(
                response_data.get("body") if self.log_level == LogLevel.FULL else None
            ),
            response_headers=(
                response_data["headers"] if self.log_level != LogLevel.BASIC else {}
            ),
            processing_time_ms=processing_time,
            database_time_ms=(
                additional_metrics.get("database_time_ms")
                if additional_metrics
                else None
            ),
            cache_time_ms=(
                additional_metrics.get("cache_time_ms") if additional_metrics else None
            ),
            endpoint_name=(
                additional_metrics.get("endpoint_name") if additional_metrics else None
            ),
            errors=additional_metrics.get("errors", []) if additional_metrics else [],
            warnings=(
                additional_metrics.get("warnings", []) if additional_metrics else []
            ),
            tags=additional_metrics.get("tags", []) if additional_metrics else [],
        )

        return log_entry

    async def store_log_entry(self, log_entry: APILogEntry):
        """Store log entry in configured storage systems"""
        try:
            # Store in Redis for real-time access
            if self.store_in_redis and self.redis_client:
                await self._store_in_redis(log_entry)

            # Store in file for persistent logging
            if self.store_in_file:
                await self._store_in_file(log_entry)

            # Update performance metrics
            await self._update_performance_metrics(log_entry)

        except Exception as e:
            logger.error(f"Failed to store log entry {log_entry.request_id}: {e}")

    async def _store_in_redis(self, log_entry: APILogEntry):
        """Store log entry in Redis"""
        try:
            # Store individual log entry
            log_key = f"api_log:{log_entry.request_id}"
            log_data = json.dumps(asdict(log_entry), default=str)
            await self.redis_client.setex(
                log_key, self.redis_retention_hours * 3600, log_data
            )

            # Add to time-ordered index
            timestamp = time.time()
            await self.redis_client.zadd(
                "api_logs_timeline", {log_entry.request_id: timestamp}
            )

            # Add to endpoint-specific index
            endpoint_key = f"api_logs_endpoint:{log_entry.path}"
            await self.redis_client.zadd(
                endpoint_key, {log_entry.request_id: timestamp}
            )

            # Add to status code index
            status_key = f"api_logs_status:{log_entry.status_code}"
            await self.redis_client.zadd(status_key, {log_entry.request_id: timestamp})

        except Exception as e:
            logger.error(f"Failed to store log entry in Redis: {e}")

    async def _store_in_file(self, log_entry: APILogEntry):
        """Store log entry in file"""
        try:
            if self.log_format == LogFormat.JSON:
                log_line = json.dumps(asdict(log_entry), default=str) + "\n"
            else:
                # Structured text format
                log_line = (
                    f"{log_entry.timestamp} [{log_entry.request_id}] "
                    f"{log_entry.method} {log_entry.path} "
                    f"-> {log_entry.status_code} "
                    f"({log_entry.processing_time_ms:.2f}ms) "
                    f"User: {log_entry.user_id or 'anonymous'} "
                    f"IP: {log_entry.client_ip}\n"
                )

            async with aiofiles.open(self.log_file_path, "a") as f:
                await f.write(log_line)

        except Exception as e:
            logger.error(f"Failed to store log entry in file: {e}")

    async def _update_performance_metrics(self, log_entry: APILogEntry):
        """Update performance metrics in Redis"""
        try:
            if not self.redis_client:
                return

            # Update endpoint performance metrics
            endpoint_key = f"perf_metrics:endpoint:{log_entry.path}"
            pipe = self.redis_client.pipeline()

            # Add response time to running average
            pipe.lpush(f"{endpoint_key}:response_times", log_entry.processing_time_ms)
            pipe.ltrim(
                f"{endpoint_key}:response_times", 0, 999
            )  # Keep last 1000 requests

            # Update request count
            pipe.incr(f"{endpoint_key}:count")

            # Update error count if applicable
            if log_entry.status_code >= 400:
                pipe.incr(f"{endpoint_key}:errors")

            await pipe.execute()

        except Exception as e:
            logger.error(f"Failed to update performance metrics: {e}")

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Remove sensitive information from headers"""
        sensitive_headers = {
            "authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "x-auth-token",
            "x-session-id",
        }

        sanitized = {}
        for key, value in headers.items():
            if key.lower() in sensitive_headers:
                sanitized[key] = "[REDACTED]"
            elif key.lower().startswith("x-") and "token" in key.lower():
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value

        return sanitized

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address considering proxies"""
        # Check for forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host

        return "unknown"

    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request context"""
        # Try to get from request state (set by auth middleware)
        if hasattr(request.state, "user_id"):
            return str(request.state.user_id)

        # Try to get from JWT token
        if hasattr(request.state, "user") and hasattr(request.state.user, "id"):
            return str(request.state.user.id)

        return None

    async def get_request_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        endpoint: Optional[str] = None,
        status_code: Optional[int] = None,
        limit: int = 100,
    ) -> List[APILogEntry]:
        """Retrieve request logs with filtering"""
        try:
            if not self.redis_client:
                return []

            # Determine which index to use
            if endpoint:
                index_key = f"api_logs_endpoint:{endpoint}"
            elif status_code:
                index_key = f"api_logs_status:{status_code}"
            else:
                index_key = "api_logs_timeline"

            # Get log IDs from index
            start_score = start_time.timestamp() if start_time else "-inf"
            end_score = end_time.timestamp() if end_time else "+inf"

            log_ids = await self.redis_client.zrevrangebyscore(
                index_key, end_score, start_score, start=0, num=limit
            )

            # Retrieve log entries
            logs = []
            for log_id in log_ids:
                log_key = f"api_log:{log_id}"
                log_data = await self.redis_client.get(log_key)
                if log_data:
                    log_dict = json.loads(log_data)
                    # Convert back to APILogEntry object
                    log_entry = APILogEntry(**log_dict)
                    logs.append(log_entry)

            return logs

        except Exception as e:
            logger.error(f"Failed to retrieve request logs: {e}")
            return []

    async def get_performance_summary(
        self, endpoint: Optional[str] = None, time_window_hours: int = 24
    ) -> Dict[str, Any]:
        """Get performance summary for endpoints"""
        try:
            if not self.redis_client:
                return {}

            summary = {}

            if endpoint:
                endpoints = [endpoint]
            else:
                # Get all endpoints with metrics
                pattern = "perf_metrics:endpoint:*"
                keys = await self.redis_client.keys(pattern)
                endpoints = [
                    key.split(":", 2)[2] for key in keys if key.endswith(":count")
                ]

            for ep in endpoints:
                ep_key = f"perf_metrics:endpoint:{ep}"

                # Get basic counts
                request_count = await self.redis_client.get(f"{ep_key}:count") or 0
                error_count = await self.redis_client.get(f"{ep_key}:errors") or 0

                # Get response times for average calculation
                response_times = await self.redis_client.lrange(
                    f"{ep_key}:response_times", 0, -1
                )
                response_times = [float(rt) for rt in response_times]

                avg_response_time = (
                    sum(response_times) / len(response_times) if response_times else 0
                )
                max_response_time = max(response_times) if response_times else 0
                min_response_time = min(response_times) if response_times else 0

                summary[ep] = {
                    "request_count": int(request_count),
                    "error_count": int(error_count),
                    "error_rate": (int(error_count) / max(int(request_count), 1)) * 100,
                    "avg_response_time_ms": avg_response_time,
                    "max_response_time_ms": max_response_time,
                    "min_response_time_ms": min_response_time,
                }

            return summary

        except Exception as e:
            logger.error(f"Failed to get performance summary: {e}")
            return {}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging"""

    def __init__(self, app, logger: RequestResponseLogger):
        super().__init__(app)
        self.logger = logger

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Check if we should log this request
        if not self.logger.should_log_request(request):
            return await call_next(request)

        # Generate request ID
        request_id = self.logger.generate_request_id()
        request.state.request_id = request_id

        # Record start time
        start_time = time.time()

        # Extract request data
        try:
            request_data = await self.logger.extract_request_data(request)
        except Exception as e:
            logger.warning(f"Failed to extract request data: {e}")
            request_data = {
                "method": request.method,
                "path": request.url.path,
                "client_ip": "unknown",
            }

        # Track request start
        self.logger.active_requests[request_id] = {
            "start_time": start_time,
            "request_data": request_data,
        }

        try:
            # Process request
            response = await call_next(request)

            # Record end time and calculate processing time
            end_time = time.time()
            processing_time_ms = (end_time - start_time) * 1000

            # Extract response data
            response_data = self.logger.extract_response_data(response)

            # Create and store log entry
            log_entry = await self.logger.create_log_entry(
                request_id=request_id,
                request_data=request_data,
                response_data=response_data,
                processing_time=processing_time_ms,
            )

            # Store asynchronously to avoid blocking response
            asyncio.create_task(self.logger.store_log_entry(log_entry))

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Log error and re-raise
            end_time = time.time()
            processing_time_ms = (end_time - start_time) * 1000

            error_response_data = {
                "status_code": 500,
                "headers": {},
                "content_length": "0",
            }

            log_entry = await self.logger.create_log_entry(
                request_id=request_id,
                request_data=request_data,
                response_data=error_response_data,
                processing_time=processing_time_ms,
                additional_metrics={"errors": [str(e)]},
            )

            asyncio.create_task(self.logger.store_log_entry(log_entry))

            raise

        finally:
            # Clean up active request tracking
            self.logger.active_requests.pop(request_id, None)


# Global logger instance
_request_logger = None


async def get_request_logger(config: Optional[Dict] = None) -> RequestResponseLogger:
    """Get global request logger instance"""
    global _request_logger

    if _request_logger is None:
        _request_logger = RequestResponseLogger(config)
        await _request_logger.initialize()

    return _request_logger


def setup_request_logging(app: FastAPI, config: Optional[Dict] = None):
    """Setup request logging for FastAPI application"""

    async def startup():
        logger = await get_request_logger(config)
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

    app.add_event_handler("startup", startup)
    return app
