"""
API Gateway Service - Phase 3 Week 37
Advanced API Gateway with microservices support, request routing, and service discovery
"""

import asyncio
import hashlib
import json
import random
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import aiohttp

from src.services.analytics_service import (
    MetricPoint,
    MetricType,
    get_analytics_service,
)
from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api_gateway")


class RoutingStrategy(Enum):
    """Request routing strategies"""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    IP_HASH = "ip_hash"
    RESPONSE_TIME = "response_time"
    HEALTH_BASED = "health_based"


class ServiceStatus(Enum):
    """Service health status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class LoadBalancerAlgorithm(Enum):
    """Load balancer algorithms"""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    RANDOM = "random"
    CONSISTENT_HASH = "consistent_hash"


@dataclass
class ServiceInstance:
    """Represents a service instance in the registry"""

    service_id: str
    service_name: str
    version: str
    host: str
    port: int
    health_check_url: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime status
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_health_check: Optional[datetime] = None
    consecutive_failures: int = 0
    response_time_ms: float = 0.0
    active_connections: int = 0

    # Load balancing
    weight: int = 100
    last_used: Optional[datetime] = None

    def get_base_url(self) -> str:
        """Get the base URL for this service instance"""
        return f"http://{self.host}:{self.port}"

    def is_healthy(self) -> bool:
        """Check if service instance is considered healthy"""
        return (
            self.status in [ServiceStatus.HEALTHY, ServiceStatus.DEGRADED]
            and self.consecutive_failures < 3
        )


@dataclass
class RouteRule:
    """API Gateway routing rule"""

    rule_id: str
    path_pattern: str  # e.g., "/api/v1/videos/*"
    target_service: str
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])

    # Routing configuration
    routing_strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
    timeout_seconds: int = 30
    retry_attempts: int = 3
    circuit_breaker_enabled: bool = True

    # Request/Response transformation
    request_headers_add: Dict[str, str] = field(default_factory=dict)
    request_headers_remove: List[str] = field(default_factory=list)
    response_headers_add: Dict[str, str] = field(default_factory=dict)

    # Rate limiting
    rate_limit_requests: Optional[int] = None
    rate_limit_window_seconds: int = 60

    # Authentication
    require_authentication: bool = True
    allowed_roles: List[str] = field(default_factory=list)

    # Versioning
    api_version: str = "v1"
    version_strategy: str = "header"  # header, path, query

    # Caching
    cache_enabled: bool = False
    cache_ttl_seconds: int = 300


@dataclass
class RequestContext:
    """Context for a gateway request"""

    request_id: str
    correlation_id: str
    client_ip: str
    user_agent: str
    auth_token: Optional[str] = None
    user_id: Optional[str] = None
    api_version: str = "v1"

    # Routing information
    matched_rule: Optional[RouteRule] = None
    target_service: Optional[str] = None
    target_instance: Optional[ServiceInstance] = None

    # Timing
    start_time: float = field(default_factory=time.time)
    routing_time: float = 0.0
    service_call_time: float = 0.0
    total_time: float = 0.0

    # Tracing
    trace_id: str = field(
        default_factory=lambda: hashlib.md5(str(time.time()).encode(), usedforsecurity=False).hexdigest()[:16]
    )
    parent_span_id: Optional[str] = None
    span_id: str = field(
        default_factory=lambda: hashlib.md5(str(random.random()).encode(), usedforsecurity=False).hexdigest()[
            :8
        ]
    )


class ServiceRegistry:
    """Service discovery and registry"""

    def __init__(self):
        self.services: Dict[str, List[ServiceInstance]] = defaultdict(list)
        self.service_metadata: Dict[str, Dict[str, Any]] = {}
        self.health_check_interval = 30  # seconds
        self.cache_manager = MediaCacheManager()

        # Start background tasks
        asyncio.create_task(self._periodic_health_checks())

        logger.info("🔍 Service registry initialized")

    async def register_service(self, instance: ServiceInstance) -> bool:
        """Register a new service instance"""
        try:
            # Add to registry
            self.services[instance.service_name].append(instance)

            # Store metadata
            self.service_metadata[instance.service_id] = {
                "registered_at": datetime.utcnow(),
                "version": instance.version,
                "metadata": instance.metadata,
            }

            # Initial health check
            await self._check_service_health(instance)

            # Cache registry state
            await self._update_registry_cache()

            logger.info(
                f"📝 Service registered: {instance.service_name} ({instance.service_id})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to register service {instance.service_id}: {e}")
            return False

    async def deregister_service(self, service_id: str) -> bool:
        """Deregister a service instance"""
        try:
            for service_name, instances in self.services.items():
                self.services[service_name] = [
                    inst for inst in instances if inst.service_id != service_id
                ]

            if service_id in self.service_metadata:
                del self.service_metadata[service_id]

            await self._update_registry_cache()

            logger.info(f"🗑️ Service deregistered: {service_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to deregister service {service_id}: {e}")
            return False

    def get_healthy_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get all healthy instances of a service"""
        instances = self.services.get(service_name, [])
        return [inst for inst in instances if inst.is_healthy()]

    def get_service_by_id(self, service_id: str) -> Optional[ServiceInstance]:
        """Get service instance by ID"""
        for instances in self.services.values():
            for instance in instances:
                if instance.service_id == service_id:
                    return instance
        return None

    async def _periodic_health_checks(self):
        """Background task for periodic health checks"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)

                # Health check all registered services
                tasks = []
                for instances in self.services.values():
                    for instance in instances:
                        tasks.append(self._check_service_health(instance))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Update registry cache
                await self._update_registry_cache()

            except Exception as e:
                logger.error(f"Health check cycle failed: {e}")

    async def _check_service_health(self, instance: ServiceInstance):
        """Check health of a single service instance"""
        try:
            start_time = time.time()

            async with aiohttp.ClientSession() as session:
                health_url = urljoin(instance.get_base_url(), instance.health_check_url)

                async with session.get(
                    health_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response_time = (time.time() - start_time) * 1000
                    instance.response_time_ms = response_time
                    instance.last_health_check = datetime.utcnow()

                    if response.status == 200:
                        instance.status = ServiceStatus.HEALTHY
                        instance.consecutive_failures = 0
                        logger.debug(
                            f"✅ Health check passed: {instance.service_id} ({response_time:.1f}ms)"
                        )
                    else:
                        instance.status = ServiceStatus.DEGRADED
                        instance.consecutive_failures += 1
                        logger.warning(
                            f"⚠️ Health check degraded: {instance.service_id} - {response.status}"
                        )

        except asyncio.TimeoutError:
            instance.consecutive_failures += 1
            instance.status = (
                ServiceStatus.UNHEALTHY
                if instance.consecutive_failures >= 3
                else ServiceStatus.DEGRADED
            )
            logger.warning(f"⏱️ Health check timeout: {instance.service_id}")

        except Exception as e:
            instance.consecutive_failures += 1
            instance.status = (
                ServiceStatus.UNHEALTHY
                if instance.consecutive_failures >= 3
                else ServiceStatus.DEGRADED
            )
            logger.error(f"❌ Health check failed: {instance.service_id} - {e}")

    async def _update_registry_cache(self):
        """Update service registry cache"""
        try:
            registry_data = {
                "services": {},
                "updated_at": datetime.utcnow().isoformat(),
            }

            for service_name, instances in self.services.items():
                registry_data["services"][service_name] = [
                    asdict(instance) for instance in instances
                ]

            await self.cache_manager.set(
                "api_gateway:service_registry",
                json.dumps(registry_data, default=str),
                ttl=600,  # 10 minutes
            )

        except Exception as e:
            logger.error(f"Failed to update registry cache: {e}")


class LoadBalancer:
    """Load balancer for service instances"""

    def __init__(
        self, algorithm: LoadBalancerAlgorithm = LoadBalancerAlgorithm.ROUND_ROBIN
    ):
        self.algorithm = algorithm
        self.round_robin_counters: Dict[str, int] = defaultdict(int)
        self.consistent_hash_ring: Dict[str, Dict[int, ServiceInstance]] = defaultdict(
            dict
        )

    def select_instance(
        self, instances: List[ServiceInstance], context: RequestContext
    ) -> Optional[ServiceInstance]:
        """Select best instance based on load balancing algorithm"""
        if not instances:
            return None

        healthy_instances = [inst for inst in instances if inst.is_healthy()]
        if not healthy_instances:
            # Fallback to any available instance if no healthy ones
            healthy_instances = instances

        if self.algorithm == LoadBalancerAlgorithm.ROUND_ROBIN:
            return self._round_robin_select(healthy_instances, context.target_service)

        elif self.algorithm == LoadBalancerAlgorithm.LEAST_CONNECTIONS:
            return self._least_connections_select(healthy_instances)

        elif self.algorithm == LoadBalancerAlgorithm.WEIGHTED:
            return self._weighted_select(healthy_instances)

        elif self.algorithm == LoadBalancerAlgorithm.RANDOM:
            return random.choice(healthy_instances)

        elif self.algorithm == LoadBalancerAlgorithm.CONSISTENT_HASH:
            return self._consistent_hash_select(healthy_instances, context)

        else:
            return healthy_instances[0]  # Fallback

    def _round_robin_select(
        self, instances: List[ServiceInstance], service_name: str
    ) -> ServiceInstance:
        """Round-robin selection"""
        counter = self.round_robin_counters[service_name]
        selected = instances[counter % len(instances)]
        self.round_robin_counters[service_name] = counter + 1
        return selected

    def _least_connections_select(
        self, instances: List[ServiceInstance]
    ) -> ServiceInstance:
        """Select instance with least active connections"""
        return min(instances, key=lambda x: x.active_connections)

    def _weighted_select(self, instances: List[ServiceInstance]) -> ServiceInstance:
        """Weighted random selection"""
        weights = [inst.weight for inst in instances]
        return random.choices(instances, weights=weights)[0]

    def _consistent_hash_select(
        self, instances: List[ServiceInstance], context: RequestContext
    ) -> ServiceInstance:
        """Consistent hash selection based on client IP or user ID"""
        hash_key = context.user_id or context.client_ip
        hash_value = hash(hash_key) % 1000

        # Find closest instance in hash ring
        service_name = context.target_service
        if service_name not in self.consistent_hash_ring or not instances:
            # Rebuild hash ring for this service
            self._rebuild_hash_ring(service_name, instances)

        hash_ring = self.consistent_hash_ring[service_name]
        if not hash_ring:
            return instances[0] if instances else None

        # Find the closest hash value
        sorted_hashes = sorted(hash_ring.keys())
        for ring_hash in sorted_hashes:
            if ring_hash >= hash_value:
                return hash_ring[ring_hash]

        # Wrap around to first instance
        return hash_ring[sorted_hashes[0]]

    def _rebuild_hash_ring(self, service_name: str, instances: List[ServiceInstance]):
        """Rebuild consistent hash ring for service"""
        self.consistent_hash_ring[service_name].clear()

        for instance in instances:
            # Create multiple hash points for better distribution
            for i in range(3):  # 3 virtual nodes per instance
                hash_key = f"{instance.service_id}:{i}"
                hash_value = hash(hash_key) % 1000
                self.consistent_hash_ring[service_name][hash_value] = instance


class APIGateway:
    """Main API Gateway service"""

    def __init__(self):
        self.service_registry = ServiceRegistry()
        self.load_balancer = LoadBalancer(LoadBalancerAlgorithm.ROUND_ROBIN)
        self.cache_manager = MediaCacheManager()

        # Routing configuration
        self.routing_rules: List[RouteRule] = []
        self.default_timeout = 30
        self.max_retries = 3

        # Request tracking
        self.active_requests: Dict[str, RequestContext] = {}
        self.request_metrics = deque(maxlen=10000)

        # Rate limiting
        self.rate_limits: Dict[str, Dict[str, Any]] = defaultdict(dict)

        logger.info("🚪 API Gateway initialized")

    async def add_routing_rule(self, rule: RouteRule):
        """Add a new routing rule"""
        self.routing_rules.append(rule)

        # Cache routing rules
        await self.cache_manager.set(
            "api_gateway:routing_rules",
            json.dumps([asdict(rule) for rule in self.routing_rules], default=str),
            ttl=3600,
        )

        logger.info(
            f"➕ Routing rule added: {rule.path_pattern} -> {rule.target_service}"
        )

    def match_route(self, path: str, method: str) -> Optional[RouteRule]:
        """Find matching route rule for request"""
        for rule in self.routing_rules:
            if method in rule.methods:
                # Simple pattern matching - could be enhanced with regex
                if rule.path_pattern.endswith("/*"):
                    prefix = rule.path_pattern[:-2]
                    if path.startswith(prefix):
                        return rule
                elif rule.path_pattern == path:
                    return rule

        return None

    async def process_request(
        self,
        path: str,
        method: str,
        headers: Dict[str, str],
        body: bytes,
        query_params: Dict[str, str],
        client_ip: str,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Process incoming request through gateway"""

        # Create request context
        context = RequestContext(
            request_id=hashlib.md5(f"{time.time()}:{client_ip}".encode(), usedforsecurity=False).hexdigest()[
                :12
            ],
            correlation_id=headers.get(
                "X-Correlation-ID",
                hashlib.md5(str(time.time()).encode(), usedforsecurity=False).hexdigest()[:16],
            ),
            client_ip=client_ip,
            user_agent=headers.get("User-Agent", "unknown"),
            auth_token=headers.get("Authorization"),
            api_version=self._extract_api_version(headers, query_params, path),
        )

        # Add to active requests tracking
        self.active_requests[context.request_id] = context

        try:
            # Route matching
            routing_start = time.time()
            rule = self.match_route(path, method)
            context.routing_time = (time.time() - routing_start) * 1000

            if not rule:
                await self._record_request_metrics(context, 404, "No route found")
                return (
                    404,
                    {"Content-Type": "application/json"},
                    b'{"error": "Route not found"}',
                )

            context.matched_rule = rule
            context.target_service = rule.target_service

            # Get healthy service instances
            instances = self.service_registry.get_healthy_instances(rule.target_service)
            if not instances:
                await self._record_request_metrics(context, 503, "No healthy instances")
                return (
                    503,
                    {"Content-Type": "application/json"},
                    b'{"error": "Service unavailable"}',
                )

            # Load balancing
            selected_instance = self.load_balancer.select_instance(instances, context)
            if not selected_instance:
                await self._record_request_metrics(context, 503, "No instance selected")
                return (
                    503,
                    {"Content-Type": "application/json"},
                    b'{"error": "Service unavailable"}',
                )

            context.target_instance = selected_instance

            # Rate limiting check
            if not await self._check_rate_limit(context, rule):
                await self._record_request_metrics(context, 429, "Rate limit exceeded")
                return (
                    429,
                    {"Content-Type": "application/json"},
                    b'{"error": "Rate limit exceeded"}',
                )

            # Forward request to service
            status_code, response_headers, response_body = await self._forward_request(
                context, rule, path, method, headers, body, query_params
            )

            # Record metrics
            await self._record_request_metrics(context, status_code, "success")

            return status_code, response_headers, response_body

        except Exception as e:
            logger.error(f"Gateway request processing failed: {e}")
            await self._record_request_metrics(context, 500, str(e))
            return (
                500,
                {"Content-Type": "application/json"},
                b'{"error": "Internal gateway error"}',
            )

        finally:
            # Remove from active requests
            if context.request_id in self.active_requests:
                del self.active_requests[context.request_id]

            # Update total time
            context.total_time = (time.time() - context.start_time) * 1000

    async def _forward_request(
        self,
        context: RequestContext,
        rule: RouteRule,
        path: str,
        method: str,
        headers: Dict[str, str],
        body: bytes,
        query_params: Dict[str, str],
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Forward request to target service"""

        service_start = time.time()
        selected_instance = context.target_instance

        try:
            # Build target URL
            target_url = urljoin(selected_instance.get_base_url(), path)

            # Prepare headers
            forwarded_headers = headers.copy()

            # Add custom headers
            forwarded_headers.update(rule.request_headers_add)

            # Remove specified headers
            for header_name in rule.request_headers_remove:
                forwarded_headers.pop(header_name, None)

            # Add gateway headers
            forwarded_headers.update(
                {
                    "X-Gateway-Request-ID": context.request_id,
                    "X-Correlation-ID": context.correlation_id,
                    "X-Forwarded-For": context.client_ip,
                    "X-Gateway-Service": selected_instance.service_id,
                    "X-Trace-ID": context.trace_id,
                    "X-Span-ID": context.span_id,
                }
            )

            # Track active connection
            selected_instance.active_connections += 1

            # Make request with retries
            status_code, response_headers, response_body = (
                await self._make_request_with_retries(
                    target_url, method, forwarded_headers, body, query_params, rule
                )
            )

            # Add response headers
            response_headers.update(rule.response_headers_add)
            response_headers.update(
                {
                    "X-Gateway-Service": selected_instance.service_id,
                    "X-Gateway-Request-ID": context.request_id,
                    "X-Response-Time": f"{(time.time() - service_start) * 1000:.1f}ms",
                }
            )

            context.service_call_time = (time.time() - service_start) * 1000
            return status_code, response_headers, response_body

        except Exception as e:
            logger.error(f"Request forwarding failed: {e}")
            return (
                502,
                {"Content-Type": "application/json"},
                b'{"error": "Bad gateway"}',
            )

        finally:
            # Release connection tracking
            selected_instance.active_connections = max(
                0, selected_instance.active_connections - 1
            )

    async def _make_request_with_retries(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: bytes,
        query_params: Dict[str, str],
        rule: RouteRule,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Make HTTP request with retry logic"""

        last_exception = None

        for attempt in range(rule.retry_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method,
                        url,
                        headers=headers,
                        data=body,
                        params=query_params,
                        timeout=aiohttp.ClientTimeout(total=rule.timeout_seconds),
                    ) as response:

                        response_headers = dict(response.headers)
                        response_body = await response.read()

                        # Return on success or client error (don't retry 4xx)
                        if response.status < 500:
                            return response.status, response_headers, response_body

                        # Server error - retry
                        if attempt < rule.retry_attempts - 1:
                            await asyncio.sleep(
                                0.1 * (2**attempt)
                            )  # Exponential backoff
                            continue

                        return response.status, response_headers, response_body

            except Exception as e:
                last_exception = e
                if attempt < rule.retry_attempts - 1:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue

        # All retries failed
        logger.error(f"All retries failed for {url}: {last_exception}")
        return (
            502,
            {"Content-Type": "application/json"},
            b'{"error": "Service request failed"}',
        )

    def _extract_api_version(
        self, headers: Dict[str, str], query_params: Dict[str, str], path: str
    ) -> str:
        """Extract API version from request"""
        # Header-based versioning
        if "Accept-Version" in headers:
            return headers["Accept-Version"]

        # Query parameter versioning
        if "version" in query_params:
            return query_params["version"]

        # Path-based versioning
        if path.startswith("/api/v"):
            parts = path.split("/")
            if len(parts) >= 3 and parts[2].startswith("v"):
                return parts[2]

        return "v1"  # Default version

    async def _check_rate_limit(self, context: RequestContext, rule: RouteRule) -> bool:
        """Check if request is within rate limits"""
        if not rule.rate_limit_requests:
            return True

        # Rate limiting key (per client IP for now)
        rate_key = f"{rule.rule_id}:{context.client_ip}"
        current_time = time.time()

        if rate_key not in self.rate_limits:
            self.rate_limits[rate_key] = {"requests": 0, "window_start": current_time}

        rate_data = self.rate_limits[rate_key]

        # Reset window if expired
        if current_time - rate_data["window_start"] >= rule.rate_limit_window_seconds:
            rate_data["requests"] = 0
            rate_data["window_start"] = current_time

        # Check limit
        if rate_data["requests"] >= rule.rate_limit_requests:
            return False

        # Increment counter
        rate_data["requests"] += 1
        return True

    async def _record_request_metrics(
        self, context: RequestContext, status_code: int, result: str
    ):
        """Record request metrics for analytics"""
        try:
            analytics_service = await get_analytics_service()

            # Record gateway metrics
            await analytics_service.record_metric(
                MetricPoint(
                    timestamp=datetime.utcnow(),
                    metric_name="gateway.requests.total",
                    metric_type=MetricType.APPLICATION,
                    value=1,
                    tags={
                        "status_code": str(status_code),
                        "target_service": context.target_service or "unknown",
                        "api_version": context.api_version,
                        "result": result,
                    },
                )
            )

            # Record response time
            await analytics_service.record_metric(
                MetricPoint(
                    timestamp=datetime.utcnow(),
                    metric_name="gateway.response_time.total_ms",
                    metric_type=MetricType.PERFORMANCE,
                    value=context.total_time,
                    tags={"target_service": context.target_service or "unknown"},
                )
            )

            # Record routing time
            await analytics_service.record_metric(
                MetricPoint(
                    timestamp=datetime.utcnow(),
                    metric_name="gateway.response_time.routing_ms",
                    metric_type=MetricType.PERFORMANCE,
                    value=context.routing_time,
                    tags={"target_service": context.target_service or "unknown"},
                )
            )

        except Exception as e:
            logger.error(f"Failed to record gateway metrics: {e}")

    async def get_gateway_stats(self) -> Dict[str, Any]:
        """Get gateway statistics"""
        try:
            total_services = sum(
                len(instances) for instances in self.service_registry.services.values()
            )
            healthy_services = sum(
                len([inst for inst in instances if inst.is_healthy()])
                for instances in self.service_registry.services.values()
            )

            return {
                "gateway": {
                    "active_requests": len(self.active_requests),
                    "routing_rules": len(self.routing_rules),
                    "total_services": total_services,
                    "healthy_services": healthy_services,
                    "load_balancer": self.load_balancer.algorithm.value,
                },
                "services": {
                    service_name: {
                        "total_instances": len(instances),
                        "healthy_instances": len(
                            [inst for inst in instances if inst.is_healthy()]
                        ),
                        "instances": [
                            {
                                "service_id": inst.service_id,
                                "status": inst.status.value,
                                "response_time_ms": inst.response_time_ms,
                                "active_connections": inst.active_connections,
                            }
                            for inst in instances
                        ],
                    }
                    for service_name, instances in self.service_registry.services.items()
                },
            }

        except Exception as e:
            logger.error(f"Failed to get gateway stats: {e}")
            return {"error": str(e)}


# Global gateway instance
api_gateway = None


async def get_api_gateway() -> APIGateway:
    """Get or create API gateway instance"""
    global api_gateway
    if api_gateway is None:
        api_gateway = APIGateway()
    return api_gateway
