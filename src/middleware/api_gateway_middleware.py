"""
API Gateway Middleware - Phase 3 Week 37
FastAPI middleware integration for API Gateway functionality
"""

import asyncio

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.services.api_gateway import (
    RouteRule,
    RoutingStrategy,
    ServiceInstance,
    get_api_gateway,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.middleware.api_gateway")


class APIGatewayMiddleware(BaseHTTPMiddleware):
    """API Gateway middleware for request routing and service discovery"""

    def __init__(
        self, app, gateway_enabled: bool = True, gateway_prefix: str = "/gateway"
    ):
        super().__init__(app)
        self.gateway_enabled = gateway_enabled
        self.gateway_prefix = gateway_prefix

        # Initialize with default services
        asyncio.create_task(self._initialize_default_services())

        logger.info(
            f"🚪 API Gateway middleware initialized (enabled: {gateway_enabled})"
        )

    async def _initialize_default_services(self):
        """Initialize default service configurations"""
        try:
            gateway = await get_api_gateway()

            # Register local MVidarr services
            local_services = [
                ServiceInstance(
                    service_id="mvidarr-api-v1",
                    service_name="mvidarr-api",
                    version="v1",
                    host="localhost",
                    port=5000,
                    health_check_url="/health",
                    metadata={
                        "description": "MVidarr Core API",
                        "type": "api",
                        "framework": "fastapi",
                    },
                ),
                ServiceInstance(
                    service_id="mvidarr-monitoring-v1",
                    service_name="mvidarr-monitoring",
                    version="v1",
                    host="localhost",
                    port=5000,
                    health_check_url="/api/monitoring/health",
                    metadata={
                        "description": "MVidarr Monitoring Service",
                        "type": "monitoring",
                        "framework": "fastapi",
                    },
                ),
                ServiceInstance(
                    service_id="mvidarr-dashboard-v1",
                    service_name="mvidarr-dashboard",
                    version="v1",
                    host="localhost",
                    port=5000,
                    health_check_url="/api/dashboard/status",
                    metadata={
                        "description": "MVidarr Dashboard Service",
                        "type": "dashboard",
                        "framework": "fastapi",
                    },
                ),
            ]

            # Register services
            for service in local_services:
                await gateway.service_registry.register_service(service)

            # Add default routing rules
            default_routes = [
                RouteRule(
                    rule_id="api-v1-videos",
                    path_pattern="/gateway/api/v1/videos/*",
                    target_service="mvidarr-api",
                    methods=["GET", "POST", "PUT", "DELETE"],
                    routing_strategy=RoutingStrategy.ROUND_ROBIN,
                    api_version="v1",
                    rate_limit_requests=100,
                    rate_limit_window_seconds=60,
                ),
                RouteRule(
                    rule_id="api-v1-artists",
                    path_pattern="/gateway/api/v1/artists/*",
                    target_service="mvidarr-api",
                    methods=["GET", "POST", "PUT", "DELETE"],
                    routing_strategy=RoutingStrategy.ROUND_ROBIN,
                    api_version="v1",
                    rate_limit_requests=100,
                ),
                RouteRule(
                    rule_id="monitoring-health",
                    path_pattern="/gateway/monitoring/*",
                    target_service="mvidarr-monitoring",
                    methods=["GET"],
                    routing_strategy=RoutingStrategy.HEALTH_BASED,
                    require_authentication=False,
                    rate_limit_requests=200,
                ),
                RouteRule(
                    rule_id="dashboard-api",
                    path_pattern="/gateway/dashboard/*",
                    target_service="mvidarr-dashboard",
                    methods=["GET", "POST"],
                    routing_strategy=RoutingStrategy.LEAST_CONNECTIONS,
                    cache_enabled=True,
                    cache_ttl_seconds=60,
                ),
            ]

            for route in default_routes:
                await gateway.add_routing_rule(route)

            logger.info("✅ Default API Gateway services and routes initialized")

        except Exception as e:
            logger.error(f"Failed to initialize default services: {e}")

    async def dispatch(self, request: Request, call_next):
        """Process request through API Gateway or pass through"""

        # Check if gateway is enabled and request matches gateway prefix
        if not self.gateway_enabled or not request.url.path.startswith(
            self.gateway_prefix
        ):
            # Pass through to normal FastAPI processing
            return await call_next(request)

        # Process through API Gateway
        return await self._process_gateway_request(request)

    async def _process_gateway_request(self, request: Request) -> Response:
        """Process request through API Gateway"""
        try:
            # Extract request information
            path = request.url.path
            method = request.method
            headers = dict(request.headers)
            query_params = dict(request.query_params)
            client_ip = self._get_client_ip(request)

            # Read request body
            body = await request.body()

            # Get API Gateway
            gateway = await get_api_gateway()

            # Process through gateway
            (
                status_code,
                response_headers,
                response_body,
            ) = await gateway.process_request(
                path, method, headers, body, query_params, client_ip
            )

            # Create response
            response = Response(
                content=response_body, status_code=status_code, headers=response_headers
            )

            # Add gateway-specific headers
            response.headers["X-API-Gateway"] = "enabled"
            response.headers["X-Gateway-Version"] = "v1"

            return response

        except Exception as e:
            logger.error(f"Gateway request processing failed: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": "Gateway processing error", "details": str(e)},
                headers={"X-API-Gateway": "error"},
            )

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check for forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        forwarded = request.headers.get("X-Forwarded")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to client host
        if hasattr(request, "client") and request.client:
            return request.client.host

        return "unknown"


class GatewayManagementMiddleware(BaseHTTPMiddleware):
    """Middleware for gateway management operations"""

    def __init__(self, app, management_prefix: str = "/gateway-admin"):
        super().__init__(app)
        self.management_prefix = management_prefix

        logger.info("🔧 Gateway management middleware initialized")

    async def dispatch(self, request: Request, call_next):
        """Handle gateway management requests"""

        if not request.url.path.startswith(self.management_prefix):
            return await call_next(request)

        # Process gateway management request
        return await self._process_management_request(request)

    async def _process_management_request(self, request: Request) -> Response:
        """Process gateway management operations"""
        try:
            path = request.url.path.replace(self.management_prefix, "")
            method = request.method

            gateway = await get_api_gateway()

            # Service registration
            if path.startswith("/services") and method == "POST":
                return await self._register_service(request, gateway)

            # Service deregistration
            elif path.startswith("/services") and method == "DELETE":
                return await self._deregister_service(request, gateway)

            # List services
            elif path.startswith("/services") and method == "GET":
                return await self._list_services(gateway)

            # Add routing rule
            elif path.startswith("/routes") and method == "POST":
                return await self._add_route(request, gateway)

            # List routes
            elif path.startswith("/routes") and method == "GET":
                return await self._list_routes(gateway)

            # Gateway statistics
            elif path.startswith("/stats") and method == "GET":
                return await self._get_stats(gateway)

            # Health check
            elif path == "/health" and method == "GET":
                return JSONResponse(
                    {
                        "status": "healthy",
                        "gateway_enabled": True,
                        "services_count": len(gateway.service_registry.services),
                        "routes_count": len(gateway.routing_rules),
                    }
                )

            else:
                return JSONResponse(
                    status_code=404, content={"error": "Management endpoint not found"}
                )

        except Exception as e:
            logger.error(f"Gateway management error: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": "Management operation failed", "details": str(e)},
            )

    async def _register_service(self, request: Request, gateway) -> Response:
        """Register a new service"""
        try:
            data = await request.json()

            service = ServiceInstance(
                service_id=data["service_id"],
                service_name=data["service_name"],
                version=data.get("version", "v1"),
                host=data["host"],
                port=data["port"],
                health_check_url=data.get("health_check_url", "/health"),
                metadata=data.get("metadata", {}),
            )

            success = await gateway.service_registry.register_service(service)

            if success:
                return JSONResponse(
                    {
                        "message": "Service registered successfully",
                        "service_id": service.service_id,
                    }
                )
            else:
                return JSONResponse(
                    status_code=400, content={"error": "Service registration failed"}
                )

        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid service registration data",
                    "details": str(e),
                },
            )

    async def _deregister_service(self, request: Request, gateway) -> Response:
        """Deregister a service"""
        try:
            service_id = request.path_params.get("service_id")
            if not service_id:
                # Try to get from query params
                service_id = request.query_params.get("service_id")

            if not service_id:
                return JSONResponse(
                    status_code=400, content={"error": "service_id required"}
                )

            success = await gateway.service_registry.deregister_service(service_id)

            if success:
                return JSONResponse({"message": "Service deregistered successfully"})
            else:
                return JSONResponse(
                    status_code=404, content={"error": "Service not found"}
                )

        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"error": "Service deregistration failed", "details": str(e)},
            )

    async def _list_services(self, gateway) -> Response:
        """List all registered services"""
        try:
            services = {}
            for service_name, instances in gateway.service_registry.services.items():
                services[service_name] = [
                    {
                        "service_id": inst.service_id,
                        "version": inst.version,
                        "host": inst.host,
                        "port": inst.port,
                        "status": inst.status.value,
                        "last_health_check": (
                            inst.last_health_check.isoformat()
                            if inst.last_health_check
                            else None
                        ),
                        "response_time_ms": inst.response_time_ms,
                        "active_connections": inst.active_connections,
                        "metadata": inst.metadata,
                    }
                    for inst in instances
                ]

            return JSONResponse(
                {
                    "services": services,
                    "total_services": sum(
                        len(instances)
                        for instances in gateway.service_registry.services.values()
                    ),
                }
            )

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to list services", "details": str(e)},
            )

    async def _add_route(self, request: Request, gateway) -> Response:
        """Add a new routing rule"""
        try:
            data = await request.json()

            route = RouteRule(
                rule_id=data["rule_id"],
                path_pattern=data["path_pattern"],
                target_service=data["target_service"],
                methods=data.get("methods", ["GET"]),
                routing_strategy=RoutingStrategy(
                    data.get("routing_strategy", "round_robin")
                ),
                timeout_seconds=data.get("timeout_seconds", 30),
                retry_attempts=data.get("retry_attempts", 3),
                rate_limit_requests=data.get("rate_limit_requests"),
                require_authentication=data.get("require_authentication", True),
                api_version=data.get("api_version", "v1"),
            )

            await gateway.add_routing_rule(route)

            return JSONResponse(
                {"message": "Routing rule added successfully", "rule_id": route.rule_id}
            )

        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid routing rule data", "details": str(e)},
            )

    async def _list_routes(self, gateway) -> Response:
        """List all routing rules"""
        try:
            routes = [
                {
                    "rule_id": rule.rule_id,
                    "path_pattern": rule.path_pattern,
                    "target_service": rule.target_service,
                    "methods": rule.methods,
                    "routing_strategy": rule.routing_strategy.value,
                    "api_version": rule.api_version,
                    "rate_limit_requests": rule.rate_limit_requests,
                    "require_authentication": rule.require_authentication,
                }
                for rule in gateway.routing_rules
            ]

            return JSONResponse({"routes": routes, "total_routes": len(routes)})

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to list routes", "details": str(e)},
            )

    async def _get_stats(self, gateway) -> Response:
        """Get gateway statistics"""
        try:
            stats = await gateway.get_gateway_stats()
            return JSONResponse(stats)

        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to get stats", "details": str(e)},
            )
