"""
Async HTTP client manager with connection pooling, retry logic, and circuit breaker patterns
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger("mvidarr.utils.async_http_client")


class CircuitBreakerState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing - reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 3  # Successes to close from half-open
    timeout_seconds: int = 60  # Time before trying half-open
    reset_timeout: int = 300  # Time to reset failure count


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics"""

    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    next_attempt_time: float = 0
    total_requests: int = 0
    total_failures: int = 0


class AsyncHttpClient:
    """
    Centralized async HTTP client with connection pooling, retry logic, and circuit breakers
    """

    def __init__(
        self,
        timeout: int = 30,
        max_connections: int = 100,
        max_connections_per_host: int = 10,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    ):
        self.timeout = aiohttp.ClientTimeout(total=timeout, connect=10)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        # Circuit breaker configuration
        self.circuit_config = circuit_breaker_config or CircuitBreakerConfig()
        self.circuit_stats: Dict[str, CircuitBreakerStats] = {}

        # Connection pooling configuration
        self.connector_config = {
            "limit": max_connections,
            "limit_per_host": max_connections_per_host,
            "ttl_dns_cache": 300,  # 5 minutes DNS cache
            "use_dns_cache": True,
            "enable_cleanup_closed": True,
        }

        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock: Optional[asyncio.Lock] = None

    async def _get_session_lock(self) -> asyncio.Lock:
        """Get session lock, creating it if needed (lazy initialization)"""
        if self._session_lock is None:
            # Always create lock in the current running loop context
            self._session_lock = asyncio.Lock()
        return self._session_lock

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proper configuration"""
        if self._session is None or self._session.closed:
            session_lock = await self._get_session_lock()
            async with session_lock:
                if self._session is None or self._session.closed:
                    connector = aiohttp.TCPConnector(**self.connector_config)

                    self._session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=self.timeout,
                        headers={
                            "User-Agent": "MVidarr/0.9.8.dev (Music Video Management System)"
                        },
                    )
                    logger.debug("Created new aiohttp session with connection pooling")

        return self._session

    def _get_circuit_key(self, url: str) -> str:
        """Generate circuit breaker key from URL (by domain)"""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return url

    def _get_circuit_stats(self, key: str) -> CircuitBreakerStats:
        """Get circuit breaker stats for a service"""
        if key not in self.circuit_stats:
            self.circuit_stats[key] = CircuitBreakerStats()
        return self.circuit_stats[key]

    def _should_attempt_request(self, stats: CircuitBreakerStats) -> bool:
        """Check if request should be attempted based on circuit breaker state"""
        current_time = time.time()

        if stats.state == CircuitBreakerState.CLOSED:
            return True

        elif stats.state == CircuitBreakerState.OPEN:
            if current_time >= stats.next_attempt_time:
                stats.state = CircuitBreakerState.HALF_OPEN
                stats.success_count = 0
                logger.info(f"Circuit breaker entering HALF_OPEN state")
                return True
            return False

        elif stats.state == CircuitBreakerState.HALF_OPEN:
            return True

        return False

    def _record_success(self, stats: CircuitBreakerStats):
        """Record successful request"""
        stats.total_requests += 1

        if stats.state == CircuitBreakerState.HALF_OPEN:
            stats.success_count += 1
            if stats.success_count >= self.circuit_config.success_threshold:
                stats.state = CircuitBreakerState.CLOSED
                stats.failure_count = 0
                logger.info("Circuit breaker returned to CLOSED state")

        elif stats.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success in normal operation
            current_time = time.time()
            if (
                current_time - stats.last_failure_time
                > self.circuit_config.reset_timeout
            ):
                stats.failure_count = 0

    def _record_failure(self, stats: CircuitBreakerStats):
        """Record failed request"""
        current_time = time.time()
        stats.total_requests += 1
        stats.total_failures += 1
        stats.failure_count += 1
        stats.last_failure_time = current_time

        if stats.state == CircuitBreakerState.HALF_OPEN:
            stats.state = CircuitBreakerState.OPEN
            stats.next_attempt_time = current_time + self.circuit_config.timeout_seconds
            logger.warning(
                "Circuit breaker returned to OPEN state after failure in HALF_OPEN"
            )

        elif (
            stats.state == CircuitBreakerState.CLOSED
            and stats.failure_count >= self.circuit_config.failure_threshold
        ):
            stats.state = CircuitBreakerState.OPEN
            stats.next_attempt_time = current_time + self.circuit_config.timeout_seconds
            logger.warning(
                f"Circuit breaker opened after {stats.failure_count} failures"
            )

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic and circuit breaker

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Request headers
            params: Query parameters
            json: JSON body data
            data: Raw body data
            **kwargs: Additional aiohttp parameters

        Returns:
            Response JSON data

        Raises:
            aiohttp.ClientError: For HTTP errors
            asyncio.TimeoutError: For timeout errors
            CircuitBreakerOpenError: When circuit breaker is open
        """
        circuit_key = self._get_circuit_key(url)
        stats = self._get_circuit_stats(circuit_key)

        # Check circuit breaker
        if not self._should_attempt_request(stats):
            raise CircuitBreakerOpenError(f"Circuit breaker open for {circuit_key}")

        session = await self._get_session()
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"HTTP {method} {url} (attempt {attempt + 1})")

                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json,
                    data=data,
                    **kwargs,
                ) as response:

                    # Check if response is successful
                    if response.status >= 400:
                        response_text = await response.text()
                        error_msg = f"HTTP {response.status}: {response_text[:200]}"

                        # Don't retry on client errors (4xx) except rate limiting
                        if 400 <= response.status < 500 and response.status != 429:
                            self._record_failure(stats)
                            raise aiohttp.ClientResponseError(
                                request_info=response.request_info,
                                history=response.history,
                                status=response.status,
                                message=error_msg,
                            )

                        # Retry on server errors (5xx) and rate limiting (429)
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=error_msg,
                        )

                    # Success - parse JSON response
                    try:
                        result = await response.json()
                        self._record_success(stats)
                        logger.debug(f"HTTP {method} {url} succeeded")
                        return result
                    except aiohttp.ContentTypeError:
                        # Response is not JSON
                        result = {
                            "text": await response.text(),
                            "status": response.status,
                        }
                        self._record_success(stats)
                        return result

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e

                # Don't retry on final attempt
                if attempt == self.max_retries:
                    break

                # Calculate backoff delay
                delay = self.backoff_factor * (2**attempt)
                logger.warning(
                    f"HTTP {method} {url} failed (attempt {attempt + 1}): {e}. "
                    f"Retrying in {delay:.1f}s"
                )

                await asyncio.sleep(delay)

        # All retries exhausted
        self._record_failure(stats)
        logger.error(
            f"HTTP {method} {url} failed after {self.max_retries + 1} attempts"
        )

        if last_exception:
            raise last_exception
        else:
            raise aiohttp.ClientError(
                f"Request failed after {self.max_retries + 1} attempts"
            )

    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make GET request"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make POST request"""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make PUT request"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make DELETE request"""
        return await self.request("DELETE", url, **kwargs)

    async def close(self):
        """Close HTTP session and cleanup resources"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("Closed aiohttp session")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    def get_circuit_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker statistics for monitoring"""
        return {
            key: {
                "state": stats.state.value,
                "failure_count": stats.failure_count,
                "success_count": stats.success_count,
                "total_requests": stats.total_requests,
                "total_failures": stats.total_failures,
                "failure_rate": (stats.total_failures / max(stats.total_requests, 1))
                * 100,
                "last_failure_time": stats.last_failure_time,
                "next_attempt_time": (
                    stats.next_attempt_time
                    if stats.state == CircuitBreakerState.OPEN
                    else None
                ),
            }
            for key, stats in self.circuit_stats.items()
        }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected"""

    pass


@asynccontextmanager
async def get_http_client(**kwargs):
    """Context manager for getting HTTP client with automatic cleanup"""
    client = AsyncHttpClient(**kwargs)
    try:
        yield client
    finally:
        await client.close()


# Global HTTP client instance for reuse across services
_global_client: Optional[AsyncHttpClient] = None
_client_lock: Optional[asyncio.Lock] = None


async def _get_global_client_lock() -> asyncio.Lock:
    """Get global client lock, creating it if needed (lazy initialization)"""
    global _client_lock
    if _client_lock is None:
        # Always create lock in the current running loop context
        _client_lock = asyncio.Lock()
    return _client_lock


async def get_global_http_client() -> AsyncHttpClient:
    """Get global HTTP client instance for reuse across the application"""
    global _global_client

    if _global_client is None:
        lock = await _get_global_client_lock()
        async with lock:
            if _global_client is None:
                _global_client = AsyncHttpClient(
                    timeout=30,
                    max_connections=100,
                    max_connections_per_host=10,
                    max_retries=3,
                    backoff_factor=1.0,
                )
                logger.info("Created global HTTP client instance")

    return _global_client


async def cleanup_global_http_client():
    """Cleanup global HTTP client - call this on application shutdown"""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None
        logger.info("Cleaned up global HTTP client instance")
