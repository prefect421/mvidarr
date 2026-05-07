"""
HTTPX-based Async HTTP Client for FastAPI Migration
Provides async HTTP operations with connection pooling, retry logic, and proper error handling
"""

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Union

import httpx
from src.utils.logger import get_logger

logger = get_logger("mvidarr.utils.httpx_async_client")


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


class AsyncHttpxClient:
    """
    HTTPX-based async HTTP client with connection pooling, retry logic, and circuit breakers
    Optimized for FastAPI migration with proper async patterns
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        user_agent: str = "MVidarr/0.9.8.dev (FastAPI Music Video Management System)",
    ):
        """Initialize the async HTTP client"""
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.user_agent = user_agent

        # Circuit breaker configuration
        self.circuit_config = circuit_breaker_config or CircuitBreakerConfig()
        self.circuit_stats: Dict[str, CircuitBreakerStats] = {}

        # HTTPX client configuration
        self.limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
        )

        self.timeout = httpx.Timeout(timeout)

        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock: Optional[asyncio.Lock] = None

    async def _get_client_lock(self) -> asyncio.Lock:
        """Get client lock, creating it if needed (lazy initialization)"""
        if self._client_lock is None:
            self._client_lock = asyncio.Lock()
        return self._client_lock

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx client with proper configuration"""
        if self._client is None or self._client.is_closed:
            client_lock = await self._get_client_lock()
            async with client_lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        limits=self.limits,
                        timeout=self.timeout,
                        headers=self.headers,
                        follow_redirects=True,
                        http2=True,  # Enable HTTP/2 for better performance
                    )
                    logger.debug(
                        "Created new httpx AsyncClient with connection pooling"
                    )

        return self._client

    def _get_circuit_key(self, url: str) -> str:
        """Generate circuit breaker key from URL (by domain)"""
        try:
            parsed = httpx.URL(url)
            return f"{parsed.scheme}://{parsed.host}"
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
        data: Optional[Union[str, bytes, Dict[str, Any]]] = None,
        files: Optional[Dict[str, Any]] = None,
        auth: Optional[tuple] = None,
        **kwargs,
    ) -> httpx.Response:
        """
        Make HTTP request with retry logic and circuit breaker

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            headers: Request headers
            params: Query parameters
            json: JSON body data
            data: Raw body data
            files: Files to upload
            auth: Authentication tuple (username, password)
            **kwargs: Additional httpx parameters

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: For HTTP errors
            httpx.TimeoutException: For timeout errors
            CircuitBreakerOpenError: When circuit breaker is open
        """
        circuit_key = self._get_circuit_key(url)
        stats = self._get_circuit_stats(circuit_key)

        # Check circuit breaker
        if not self._should_attempt_request(stats):
            raise CircuitBreakerOpenError(f"Circuit breaker open for {circuit_key}")

        client = await self._get_client()
        last_exception = None

        # Merge headers
        merged_headers = {}
        if headers:
            merged_headers.update(headers)

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(f"HTTP {method} {url} (attempt {attempt + 1})")

                response = await client.request(
                    method=method,
                    url=url,
                    headers=merged_headers,
                    params=params,
                    json=json,
                    data=data,
                    files=files,
                    auth=auth,
                    **kwargs,
                )

                # Check if response is successful
                if response.status_code >= 400:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"

                    # Don't retry on client errors (4xx) except rate limiting
                    if (
                        400 <= response.status_code < 500
                        and response.status_code != 429
                    ):
                        self._record_failure(stats)
                        response.raise_for_status()

                    # Retry on server errors (5xx) and rate limiting (429)
                    if attempt < self.max_retries:
                        raise httpx.HTTPStatusError(
                            message=error_msg,
                            request=response.request,
                            response=response,
                        )
                    else:
                        self._record_failure(stats)
                        response.raise_for_status()

                # Success
                self._record_success(stats)
                logger.debug(
                    f"HTTP {method} {url} succeeded (status: {response.status_code})"
                )
                return response

            except (httpx.HTTPError, httpx.TimeoutException) as e:
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
            raise httpx.RequestError(
                f"Request failed after {self.max_retries + 1} attempts"
            )

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Make GET request"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Make POST request"""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """Make PUT request"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """Make DELETE request"""
        return await self.request("DELETE", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> httpx.Response:
        """Make PATCH request"""
        return await self.request("PATCH", url, **kwargs)

    # Convenience methods for common response types
    async def get_json(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make GET request and return JSON response"""
        response = await self.get(url, **kwargs)
        return response.json()

    async def post_json(self, url: str, **kwargs) -> Dict[str, Any]:
        """Make POST request and return JSON response"""
        response = await self.post(url, **kwargs)
        return response.json()

    async def get_text(self, url: str, **kwargs) -> str:
        """Make GET request and return text response"""
        response = await self.get(url, **kwargs)
        return response.text

    async def close(self):
        """Close HTTP client and cleanup resources"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("Closed httpx AsyncClient")

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

    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection pool information for monitoring"""
        if self._client and not self._client.is_closed:
            return {
                "is_closed": self._client.is_closed,
                "base_url": (
                    str(self._client.base_url) if self._client.base_url else None
                ),
                "limits": {
                    "max_connections": self.limits.max_connections,
                    "max_keepalive_connections": self.limits.max_keepalive_connections,
                },
            }
        return {"is_closed": True}


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and request is rejected"""

    pass


@asynccontextmanager
async def get_httpx_client(**kwargs):
    """Context manager for getting HTTP client with automatic cleanup"""
    client = AsyncHttpxClient(**kwargs)
    try:
        yield client
    finally:
        await client.close()


# Global HTTP client instance for reuse across services
_global_client: Optional[AsyncHttpxClient] = None
_client_lock: Optional[asyncio.Lock] = None


async def _get_global_client_lock() -> asyncio.Lock:
    """Get global client lock, creating it if needed (lazy initialization)"""
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


async def get_global_httpx_client() -> AsyncHttpxClient:
    """Get global HTTP client instance for reuse across the application"""
    global _global_client

    if _global_client is None:
        lock = await _get_global_client_lock()
        async with lock:
            if _global_client is None:
                _global_client = AsyncHttpxClient(
                    timeout=30.0,
                    max_connections=100,
                    max_keepalive_connections=20,
                    max_retries=3,
                    backoff_factor=1.0,
                )
                logger.info("Created global HTTPX client instance")

    return _global_client


async def cleanup_global_httpx_client():
    """Cleanup global HTTP client - call this on application shutdown"""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None
        logger.info("Cleaned up global HTTPX client instance")


# Utility functions for common HTTP operations
async def fetch_json(url: str, **kwargs) -> Dict[str, Any]:
    """Fetch JSON data from URL using global client"""
    client = await get_global_httpx_client()
    return await client.get_json(url, **kwargs)


async def fetch_text(url: str, **kwargs) -> str:
    """Fetch text data from URL using global client"""
    client = await get_global_httpx_client()
    return await client.get_text(url, **kwargs)


async def post_json(url: str, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Post JSON data to URL using global client"""
    client = await get_global_httpx_client()
    return await client.post_json(url, json=data, **kwargs)


# Test function for the async HTTP client
async def test_httpx_async_client():
    """Test the HTTPX async HTTP client functionality"""
    try:
        logger.info("🧪 Testing AsyncHttpxClient")

        # Test basic client creation
        async with AsyncHttpxClient() as client:
            logger.info("✅ Client created successfully")

            # Test a simple HTTP request
            response = await client.get("https://httpbin.org/get")

            if response.status_code == 200:
                logger.info("✅ Basic GET request successful")

                # Test JSON parsing
                json_data = response.json()
                if "url" in json_data:
                    logger.info("✅ JSON parsing successful")

                    # Test convenience method
                    json_response = await client.get_json("https://httpbin.org/get")
                    if "url" in json_response:
                        logger.info("✅ Convenience get_json method working")
                        return True
                    else:
                        logger.error("❌ Convenience method failed")
                        return False
                else:
                    logger.error("❌ JSON parsing failed")
                    return False
            else:
                logger.error(
                    f"❌ HTTP request failed with status {response.status_code}"
                )
                return False

    except Exception as e:
        logger.error(f"❌ AsyncHttpxClient test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    """Run tests if executed directly"""
    import asyncio
    import os
    import sys

    # Add project root to path
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    async def main():
        print("🧪 Testing AsyncHttpxClient")
        print("=" * 40)

        success = await test_httpx_async_client()

        print("=" * 40)
        if success:
            print("🎉 AsyncHttpxClient tests passed!")
        else:
            print("💥 AsyncHttpxClient tests failed!")

        return success

    success = asyncio.run(main())
    exit(0 if success else 1)
