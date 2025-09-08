"""
Circuit Breaker Middleware - Phase 3 Week 35
Intelligent circuit breakers and failover mechanisms for production resilience
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.circuit_breaker")


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit breaker active, requests failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class FailureType(Enum):
    """Types of failures detected"""
    TIMEOUT = "timeout"
    ERROR_RATE = "error_rate"
    SLOW_RESPONSE = "slow_response"
    DEPENDENCY_FAILURE = "dependency_failure"
    RESOURCE_EXHAUSTION = "resource_exhaustion"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    # Failure thresholds
    failure_threshold: int = 10  # Number of failures to open circuit
    recovery_threshold: int = 5   # Successes needed in half-open to close
    error_rate_threshold: float = 0.5  # 50% error rate threshold
    slow_request_threshold_ms: int = 5000  # 5 seconds
    
    # Timing configuration
    timeout_duration_ms: int = 10000  # 10 seconds request timeout
    circuit_open_duration_ms: int = 30000  # 30 seconds circuit stays open
    half_open_max_requests: int = 3  # Max requests in half-open state
    
    # Monitoring window
    monitoring_window_seconds: int = 60  # Rolling window for failure tracking
    min_requests_for_stats: int = 10  # Minimum requests before circuit logic


@dataclass
class RequestMetric:
    """Individual request metrics"""
    timestamp: float
    endpoint: str
    response_time_ms: float
    status_code: int
    success: bool
    failure_type: Optional[FailureType] = None
    error_message: Optional[str] = None


@dataclass
class CircuitBreakerStatus:
    """Circuit breaker status information"""
    state: CircuitState
    endpoint: str
    failure_count: int
    success_count: int
    last_failure_time: Optional[float]
    last_state_change: float
    error_rate: float
    avg_response_time_ms: float
    total_requests: int
    recent_failures: List[str] = field(default_factory=list)


class CircuitBreaker:
    """Individual circuit breaker for a service/endpoint"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        
        # Metrics tracking
        self.request_metrics = deque(maxlen=1000)
        self.failure_count = 0
        self.success_count = 0
        self.half_open_requests = 0
        
        # State timing
        self.last_failure_time = None
        self.last_state_change_time = time.time()
        self.circuit_opened_time = None
        
        logger.info(f"🔌 Circuit breaker '{name}' initialized")
    
    def _clean_old_metrics(self):
        """Remove metrics outside monitoring window"""
        current_time = time.time()
        cutoff_time = current_time - self.config.monitoring_window_seconds
        
        # Remove old metrics
        while (self.request_metrics and 
               self.request_metrics[0].timestamp < cutoff_time):
            self.request_metrics.popleft()
    
    def _calculate_error_rate(self) -> float:
        """Calculate current error rate"""
        self._clean_old_metrics()
        
        if len(self.request_metrics) < self.config.min_requests_for_stats:
            return 0.0
        
        failed_requests = sum(1 for m in self.request_metrics if not m.success)
        return failed_requests / len(self.request_metrics)
    
    def _calculate_avg_response_time(self) -> float:
        """Calculate average response time"""
        self._clean_old_metrics()
        
        if not self.request_metrics:
            return 0.0
        
        return sum(m.response_time_ms for m in self.request_metrics) / len(self.request_metrics)
    
    def _should_open_circuit(self) -> bool:
        """Check if circuit should be opened"""
        # Failure count threshold
        if self.failure_count >= self.config.failure_threshold:
            return True
        
        # Error rate threshold
        error_rate = self._calculate_error_rate()
        if (error_rate >= self.config.error_rate_threshold and 
            len(self.request_metrics) >= self.config.min_requests_for_stats):
            return True
        
        return False
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset to half-open"""
        if self.state != CircuitState.OPEN:
            return False
        
        if not self.circuit_opened_time:
            return True
        
        time_since_opened = (time.time() - self.circuit_opened_time) * 1000
        return time_since_opened >= self.config.circuit_open_duration_ms
    
    def _transition_to_state(self, new_state: CircuitState, reason: str = ""):
        """Transition circuit breaker to new state"""
        old_state = self.state
        self.state = new_state
        self.last_state_change_time = time.time()
        
        if new_state == CircuitState.OPEN:
            self.circuit_opened_time = time.time()
            self.half_open_requests = 0
        elif new_state == CircuitState.HALF_OPEN:
            self.half_open_requests = 0
        elif new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0
            self.circuit_opened_time = None
        
        logger.info(f"🔌 Circuit '{self.name}' transitioned from {old_state.value} to {new_state.value}: {reason}")
    
    def can_execute(self) -> bool:
        """Check if request can be executed"""
        current_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            return True
        
        elif self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_state(CircuitState.HALF_OPEN, "Attempting recovery")
                return True
            return False
        
        elif self.state == CircuitState.HALF_OPEN:
            if self.half_open_requests < self.config.half_open_max_requests:
                return True
            return False
        
        return False
    
    def record_success(self, endpoint: str, response_time_ms: float):
        """Record successful request"""
        metric = RequestMetric(
            timestamp=time.time(),
            endpoint=endpoint,
            response_time_ms=response_time_ms,
            status_code=200,
            success=True
        )
        
        self.request_metrics.append(metric)
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            self.half_open_requests += 1
            
            if self.success_count >= self.config.recovery_threshold:
                self._transition_to_state(CircuitState.CLOSED, f"Recovery successful ({self.success_count} successes)")
        
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self, endpoint: str, response_time_ms: float, 
                      failure_type: FailureType, error_message: str = "", 
                      status_code: int = 500):
        """Record failed request"""
        metric = RequestMetric(
            timestamp=time.time(),
            endpoint=endpoint,
            response_time_ms=response_time_ms,
            status_code=status_code,
            success=False,
            failure_type=failure_type,
            error_message=error_message
        )
        
        self.request_metrics.append(metric)
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            if self._should_open_circuit():
                self._transition_to_state(CircuitState.OPEN, 
                    f"Failure threshold reached ({self.failure_count} failures, {self._calculate_error_rate():.1%} error rate)")
        
        elif self.state == CircuitState.HALF_OPEN:
            self.half_open_requests += 1
            self._transition_to_state(CircuitState.OPEN, "Failed during recovery attempt")
    
    def get_status(self) -> CircuitBreakerStatus:
        """Get current circuit breaker status"""
        self._clean_old_metrics()
        
        recent_failures = []
        for metric in list(self.request_metrics)[-5:]:
            if not metric.success and metric.error_message:
                recent_failures.append(f"{metric.failure_type.value}: {metric.error_message}")
        
        return CircuitBreakerStatus(
            state=self.state,
            endpoint=self.name,
            failure_count=self.failure_count,
            success_count=self.success_count,
            last_failure_time=self.last_failure_time,
            last_state_change=self.last_state_change_time,
            error_rate=self._calculate_error_rate(),
            avg_response_time_ms=self._calculate_avg_response_time(),
            total_requests=len(self.request_metrics),
            recent_failures=recent_failures
        )


class CircuitBreakerManager:
    """Manages multiple circuit breakers"""
    
    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None):
        self.default_config = default_config or CircuitBreakerConfig()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.cache_manager = MediaCacheManager()
        
        # Global failure tracking
        self.global_failure_count = 0
        self.system_degraded = False
        
        logger.info("🔌 Circuit breaker manager initialized")
    
    def get_circuit_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create circuit breaker for service"""
        if name not in self.circuit_breakers:
            circuit_config = config or self.default_config
            self.circuit_breakers[name] = CircuitBreaker(name, circuit_config)
        
        return self.circuit_breakers[name]
    
    def is_system_degraded(self) -> bool:
        """Check if system is globally degraded"""
        open_circuits = sum(1 for cb in self.circuit_breakers.values() 
                           if cb.state == CircuitState.OPEN)
        
        # System is degraded if >50% of circuits are open
        if len(self.circuit_breakers) > 0:
            degraded_threshold = len(self.circuit_breakers) * 0.5
            self.system_degraded = open_circuits >= degraded_threshold
        
        return self.system_degraded
    
    def get_fallback_response(self, endpoint: str, error_details: str) -> Dict[str, Any]:
        """Get fallback response when circuit is open"""
        return {
            "error": "Service temporarily unavailable",
            "circuit_breaker": "open",
            "endpoint": endpoint,
            "details": error_details,
            "retry_after": self.default_config.circuit_open_duration_ms // 1000,
            "fallback": True
        }
    
    async def get_cached_response(self, cache_key: str) -> Optional[Any]:
        """Attempt to get cached response as fallback"""
        try:
            cached = await self.cache_manager.get(cache_key)
            if cached:
                logger.info(f"🔄 Serving cached fallback for: {cache_key}")
                return cached
        except Exception as e:
            logger.error(f"Failed to get cached fallback: {e}")
        
        return None
    
    def get_all_status(self) -> Dict[str, CircuitBreakerStatus]:
        """Get status of all circuit breakers"""
        return {name: cb.get_status() for name, cb in self.circuit_breakers.items()}


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    """Circuit breaker middleware for automatic failure handling"""
    
    def __init__(self, app, config: Optional[CircuitBreakerConfig] = None):
        super().__init__(app)
        self.circuit_manager = CircuitBreakerManager(config)
        
        # Endpoint patterns for circuit breaker grouping
        self.endpoint_patterns = {
            "database": ["/api/videos", "/api/artists", "/api/playlists"],
            "cache": ["/api/performance", "/api/settings"],
            "external": ["/api/imvdb", "/api/spotify"],
            "processing": ["/api/image-processing", "/api/bulk-operations"]
        }
        
        logger.info("🔌 Circuit breaker middleware initialized")
    
    def _get_service_name(self, path: str) -> str:
        """Determine service name from endpoint path"""
        for service, patterns in self.endpoint_patterns.items():
            if any(path.startswith(pattern) for pattern in patterns):
                return service
        
        return "default"
    
    def _determine_failure_type(self, response_time_ms: float, status_code: int, 
                               exception: Optional[Exception] = None) -> FailureType:
        """Determine type of failure"""
        if response_time_ms > self.circuit_manager.default_config.timeout_duration_ms:
            return FailureType.TIMEOUT
        elif response_time_ms > self.circuit_manager.default_config.slow_request_threshold_ms:
            return FailureType.SLOW_RESPONSE
        elif status_code >= 500:
            return FailureType.DEPENDENCY_FAILURE
        elif status_code == 503:
            return FailureType.RESOURCE_EXHAUSTION
        else:
            return FailureType.ERROR_RATE
    
    async def dispatch(self, request: Request, call_next):
        """Process request with circuit breaker protection"""
        service_name = self._get_service_name(request.url.path)
        circuit_breaker = self.circuit_manager.get_circuit_breaker(service_name)
        
        # Check if circuit allows execution
        if not circuit_breaker.can_execute():
            logger.warning(f"🔌 Circuit breaker OPEN for service '{service_name}' - request blocked")
            
            # Try to serve cached response
            cache_key = f"fallback:{request.url.path}:{request.method}"
            cached_response = await self.circuit_manager.get_cached_response(cache_key)
            
            if cached_response:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"cached": True, "data": cached_response},
                    headers={"X-Circuit-Breaker": "fallback-cache"}
                )
            
            # Return circuit breaker response
            fallback_response = self.circuit_manager.get_fallback_response(
                request.url.path, 
                f"Service '{service_name}' circuit breaker is open"
            )
            
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=fallback_response,
                headers={
                    "X-Circuit-Breaker": "open",
                    "X-Service": service_name,
                    "Retry-After": str(self.circuit_manager.default_config.circuit_open_duration_ms // 1000)
                }
            )
        
        # Execute request with timeout and monitoring
        start_time = time.time()
        
        try:
            # Set up timeout for the request
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.circuit_manager.default_config.timeout_duration_ms / 1000
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record success or failure based on response
            if 200 <= response.status_code < 400:
                circuit_breaker.record_success(request.url.path, response_time_ms)
                
                # Cache successful responses for fallback
                if response.status_code == 200:
                    cache_key = f"fallback:{request.url.path}:{request.method}"
                    try:
                        # Cache for fallback use (longer TTL)
                        await self.circuit_manager.cache_manager.set(
                            cache_key, 
                            "success_response_cached", 
                            ttl=3600
                        )
                    except Exception as e:
                        logger.error(f"Failed to cache fallback response: {e}")
            
            else:
                failure_type = self._determine_failure_type(
                    response_time_ms, response.status_code
                )
                circuit_breaker.record_failure(
                    request.url.path, 
                    response_time_ms, 
                    failure_type,
                    f"HTTP {response.status_code}",
                    response.status_code
                )
            
            # Add circuit breaker headers
            response.headers["X-Circuit-Breaker"] = circuit_breaker.state.value
            response.headers["X-Service"] = service_name
            response.headers["X-Response-Time"] = f"{response_time_ms:.1f}ms"
            
            # Add system degradation warning
            if self.circuit_manager.is_system_degraded():
                response.headers["X-System-Status"] = "degraded"
            
            return response
            
        except asyncio.TimeoutError:
            response_time_ms = (time.time() - start_time) * 1000
            circuit_breaker.record_failure(
                request.url.path,
                response_time_ms,
                FailureType.TIMEOUT,
                f"Request timeout ({response_time_ms:.0f}ms)"
            )
            
            logger.error(f"⏱️ Request timeout for {service_name}: {request.url.path}")
            
            # Try cached fallback for timeouts
            cache_key = f"fallback:{request.url.path}:{request.method}"
            cached_response = await self.circuit_manager.get_cached_response(cache_key)
            
            if cached_response:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"cached": True, "timeout_fallback": True, "data": cached_response},
                    headers={"X-Circuit-Breaker": "timeout-fallback"}
                )
            
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"error": "Request timeout", "service": service_name},
                headers={"X-Circuit-Breaker": "timeout"}
            )
            
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            circuit_breaker.record_failure(
                request.url.path,
                response_time_ms,
                FailureType.DEPENDENCY_FAILURE,
                str(e)
            )
            
            logger.error(f"❌ Request failed for {service_name}: {e}")
            
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Internal server error", "service": service_name},
                headers={"X-Circuit-Breaker": "error"}
            )


# API endpoints for circuit breaker monitoring
class CircuitBreakerAPI:
    """API endpoints for circuit breaker management"""
    
    def __init__(self, circuit_manager: CircuitBreakerManager):
        self.circuit_manager = circuit_manager
    
    async def get_circuit_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers"""
        all_status = self.circuit_manager.get_all_status()
        
        return {
            "circuit_breakers": {name: {
                "state": status.state.value,
                "failure_count": status.failure_count,
                "error_rate": round(status.error_rate * 100, 1),
                "avg_response_time_ms": round(status.avg_response_time_ms, 1),
                "total_requests": status.total_requests,
                "recent_failures": status.recent_failures[:3]  # Last 3 failures
            } for name, status in all_status.items()},
            "system_degraded": self.circuit_manager.is_system_degraded(),
            "timestamp": time.time()
        }
    
    async def reset_circuit_breaker(self, service_name: str) -> Dict[str, Any]:
        """Manually reset a circuit breaker"""
        if service_name in self.circuit_manager.circuit_breakers:
            circuit = self.circuit_manager.circuit_breakers[service_name]
            circuit._transition_to_state(CircuitState.CLOSED, "Manual reset")
            
            return {
                "message": f"Circuit breaker '{service_name}' reset to CLOSED",
                "service": service_name,
                "new_state": "closed"
            }
        else:
            return {"error": f"Circuit breaker '{service_name}' not found"}