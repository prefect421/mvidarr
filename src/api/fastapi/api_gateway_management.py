"""
API Gateway Management API - Phase 3 Week 37
RESTful API for managing API Gateway services, routes, and configurations
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.api_gateway import (
    RouteRule,
    RoutingStrategy,
    ServiceInstance,
    get_api_gateway,
)
from src.services.api_versioning_service import get_api_versioning_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.gateway_management")

router = APIRouter(
    prefix="/api/gateway",
    tags=["api-gateway-management"],
    responses={
        404: {"description": "Gateway resource not found"},
        500: {"description": "Gateway service error"},
    },
)


# Request/Response Models
class ServiceRegistrationRequest(BaseModel):
    """Service registration request"""

    service_id: str = Field(description="Unique service identifier")
    service_name: str = Field(description="Service name")
    version: str = Field(default="v1", description="Service version")
    host: str = Field(description="Service host")
    port: int = Field(ge=1, le=65535, description="Service port")
    health_check_url: str = Field(
        default="/health", description="Health check endpoint"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Service metadata"
    )
    weight: int = Field(default=100, ge=1, le=1000, description="Load balancing weight")


class RouteRuleRequest(BaseModel):
    """Route rule creation request"""

    rule_id: str = Field(description="Unique rule identifier")
    path_pattern: str = Field(description="URL path pattern (supports wildcards)")
    target_service: str = Field(description="Target service name")
    methods: List[str] = Field(default=["GET"], description="HTTP methods")
    routing_strategy: str = Field(
        default="round_robin", description="Load balancing strategy"
    )
    timeout_seconds: int = Field(
        default=30, ge=1, le=300, description="Request timeout"
    )
    retry_attempts: int = Field(default=3, ge=0, le=10, description="Retry attempts")
    rate_limit_requests: Optional[int] = Field(
        None, description="Rate limit per window"
    )
    rate_limit_window_seconds: int = Field(default=60, description="Rate limit window")
    require_authentication: bool = Field(
        default=True, description="Authentication required"
    )
    api_version: str = Field(default="v1", description="API version")
    cache_enabled: bool = Field(default=False, description="Enable response caching")
    cache_ttl_seconds: int = Field(default=300, description="Cache TTL")


class ServiceResponse(BaseModel):
    """Service information response"""

    service_id: str
    service_name: str
    version: str
    host: str
    port: int
    status: str
    last_health_check: Optional[datetime]
    response_time_ms: float
    active_connections: int
    weight: int
    metadata: Dict[str, Any]


class RouteResponse(BaseModel):
    """Route rule response"""

    rule_id: str
    path_pattern: str
    target_service: str
    methods: List[str]
    routing_strategy: str
    api_version: str
    rate_limit_requests: Optional[int]
    require_authentication: bool
    cache_enabled: bool


class GatewayStatsResponse(BaseModel):
    """Gateway statistics response"""

    gateway_info: Dict[str, Any]
    services: Dict[str, Any]
    performance: Dict[str, float]
    health_summary: Dict[str, int]


class VersionInfoResponse(BaseModel):
    """API version information response"""

    version: str
    release_date: str
    compatibility_level: str
    is_active: bool
    is_default: bool
    is_deprecated: bool
    deprecation_date: Optional[str]
    sunset_date: Optional[str]
    description: str
    migration_guide: str


# Service Management Endpoints
@router.post("/services", response_model=Dict[str, Any])
async def register_service(service_request: ServiceRegistrationRequest):
    """Register a new service with the gateway"""
    try:
        gateway = await get_api_gateway()

        # Create service instance
        service = ServiceInstance(
            service_id=service_request.service_id,
            service_name=service_request.service_name,
            version=service_request.version,
            host=service_request.host,
            port=service_request.port,
            health_check_url=service_request.health_check_url,
            metadata=service_request.metadata,
            weight=service_request.weight,
        )

        # Register with gateway
        success = await gateway.service_registry.register_service(service)

        if success:
            return {
                "message": "Service registered successfully",
                "service_id": service_request.service_id,
                "registered_at": datetime.utcnow(),
            }
        else:
            raise HTTPException(status_code=400, detail="Service registration failed")

    except Exception as e:
        logger.error(f"Service registration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/services", response_model=Dict[str, Any])
async def list_services():
    """List all registered services"""
    try:
        gateway = await get_api_gateway()

        services_data = {}
        total_services = 0
        healthy_services = 0

        for service_name, instances in gateway.service_registry.services.items():
            service_instances = []
            for instance in instances:
                service_instances.append(
                    ServiceResponse(
                        service_id=instance.service_id,
                        service_name=instance.service_name,
                        version=instance.version,
                        host=instance.host,
                        port=instance.port,
                        status=instance.status.value,
                        last_health_check=instance.last_health_check,
                        response_time_ms=instance.response_time_ms,
                        active_connections=instance.active_connections,
                        weight=instance.weight,
                        metadata=instance.metadata,
                    )
                )

                total_services += 1
                if instance.is_healthy():
                    healthy_services += 1

            services_data[service_name] = service_instances

        return {
            "services": services_data,
            "summary": {
                "total_services": total_services,
                "healthy_services": healthy_services,
                "service_types": len(gateway.service_registry.services),
            },
        }

    except Exception as e:
        logger.error(f"List services error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/services/{service_id}")
async def deregister_service(service_id: str):
    """Deregister a service from the gateway"""
    try:
        gateway = await get_api_gateway()

        success = await gateway.service_registry.deregister_service(service_id)

        if success:
            return {
                "message": "Service deregistered successfully",
                "service_id": service_id,
                "deregistered_at": datetime.utcnow(),
            }
        else:
            raise HTTPException(
                status_code=404, detail=f"Service {service_id} not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Service deregistration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/services/{service_id}/health")
async def check_service_health(service_id: str):
    """Check health of a specific service"""
    try:
        gateway = await get_api_gateway()

        service = gateway.service_registry.get_service_by_id(service_id)
        if not service:
            raise HTTPException(
                status_code=404, detail=f"Service {service_id} not found"
            )

        # Trigger immediate health check
        await gateway.service_registry._check_service_health(service)

        return {
            "service_id": service_id,
            "status": service.status.value,
            "last_health_check": service.last_health_check,
            "response_time_ms": service.response_time_ms,
            "consecutive_failures": service.consecutive_failures,
            "is_healthy": service.is_healthy(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Service health check error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Route Management Endpoints
@router.post("/routes", response_model=Dict[str, Any])
async def create_route_rule(route_request: RouteRuleRequest):
    """Create a new routing rule"""
    try:
        gateway = await get_api_gateway()

        # Validate routing strategy
        try:
            routing_strategy = RoutingStrategy(route_request.routing_strategy)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid routing strategy: {route_request.routing_strategy}",
            )

        # Create route rule
        route_rule = RouteRule(
            rule_id=route_request.rule_id,
            path_pattern=route_request.path_pattern,
            target_service=route_request.target_service,
            methods=route_request.methods,
            routing_strategy=routing_strategy,
            timeout_seconds=route_request.timeout_seconds,
            retry_attempts=route_request.retry_attempts,
            rate_limit_requests=route_request.rate_limit_requests,
            rate_limit_window_seconds=route_request.rate_limit_window_seconds,
            require_authentication=route_request.require_authentication,
            api_version=route_request.api_version,
            cache_enabled=route_request.cache_enabled,
            cache_ttl_seconds=route_request.cache_ttl_seconds,
        )

        # Add to gateway
        await gateway.add_routing_rule(route_rule)

        return {
            "message": "Route rule created successfully",
            "rule_id": route_request.rule_id,
            "created_at": datetime.utcnow(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route creation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/routes", response_model=Dict[str, Any])
async def list_routes():
    """List all routing rules"""
    try:
        gateway = await get_api_gateway()

        routes_data = []
        for route in gateway.routing_rules:
            routes_data.append(
                RouteResponse(
                    rule_id=route.rule_id,
                    path_pattern=route.path_pattern,
                    target_service=route.target_service,
                    methods=route.methods,
                    routing_strategy=route.routing_strategy.value,
                    api_version=route.api_version,
                    rate_limit_requests=route.rate_limit_requests,
                    require_authentication=route.require_authentication,
                    cache_enabled=route.cache_enabled,
                )
            )

        return {"routes": routes_data, "total_routes": len(routes_data)}

    except Exception as e:
        logger.error(f"List routes error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/routes/{rule_id}")
async def delete_route_rule(rule_id: str):
    """Delete a routing rule"""
    try:
        gateway = await get_api_gateway()

        # Find and remove route
        original_count = len(gateway.routing_rules)
        gateway.routing_rules = [
            rule for rule in gateway.routing_rules if rule.rule_id != rule_id
        ]

        if len(gateway.routing_rules) == original_count:
            raise HTTPException(
                status_code=404, detail=f"Route rule {rule_id} not found"
            )

        return {
            "message": "Route rule deleted successfully",
            "rule_id": rule_id,
            "deleted_at": datetime.utcnow(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route deletion error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Gateway Statistics and Monitoring
@router.get("/stats", response_model=GatewayStatsResponse)
async def get_gateway_statistics():
    """Get comprehensive gateway statistics"""
    try:
        gateway = await get_api_gateway()
        stats = await gateway.get_gateway_stats()

        # Calculate performance metrics
        performance = {
            "avg_response_time_ms": 0.0,
            "requests_per_second": 0.0,
            "error_rate_percent": 0.0,
            "cache_hit_rate_percent": 0.0,
        }

        # Health summary
        health_summary = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}

        # Calculate health distribution
        for service_info in stats.get("services", {}).values():
            for instance in service_info.get("instances", []):
                status = instance.get("status", "unknown")
                health_summary[status] = health_summary.get(status, 0) + 1

        return GatewayStatsResponse(
            gateway_info=stats.get("gateway", {}),
            services=stats.get("services", {}),
            performance=performance,
            health_summary=health_summary,
        )

    except Exception as e:
        logger.error(f"Gateway stats error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def gateway_health_check():
    """Gateway health check endpoint"""
    try:
        gateway = await get_api_gateway()

        total_services = sum(
            len(instances) for instances in gateway.service_registry.services.values()
        )

        healthy_services = sum(
            len([inst for inst in instances if inst.is_healthy()])
            for instances in gateway.service_registry.services.values()
        )

        health_percentage = (
            (healthy_services / total_services * 100) if total_services > 0 else 100
        )

        status = "healthy"
        if health_percentage < 50:
            status = "critical"
        elif health_percentage < 80:
            status = "degraded"

        return {
            "status": status,
            "gateway_enabled": True,
            "total_services": total_services,
            "healthy_services": healthy_services,
            "health_percentage": health_percentage,
            "routing_rules": len(gateway.routing_rules),
            "active_requests": len(gateway.active_requests),
            "timestamp": datetime.utcnow(),
        }

    except Exception as e:
        logger.error(f"Gateway health check error: {e}")
        return {"status": "error", "error": str(e), "timestamp": datetime.utcnow()}


# API Versioning Endpoints
@router.get("/versions", response_model=Dict[str, Any])
async def list_api_versions():
    """List all API versions"""
    try:
        versioning_service = await get_api_versioning_service()

        versions_info = []
        for version_str in versioning_service.versions.keys():
            version_info = await versioning_service.get_version_info(version_str)
            if version_info:
                versions_info.append(VersionInfoResponse(**version_info))

        return {
            "versions": versions_info,
            "default_version": versioning_service.get_default_version(),
            "supported_versions": versioning_service.get_supported_versions(),
        }

    except Exception as e:
        logger.error(f"List versions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/versions/{version}/info", response_model=VersionInfoResponse)
async def get_version_info(version: str):
    """Get detailed information about an API version"""
    try:
        versioning_service = await get_api_versioning_service()

        version_info = await versioning_service.get_version_info(version)
        if not version_info:
            raise HTTPException(
                status_code=404, detail=f"API version {version} not found"
            )

        return VersionInfoResponse(**version_info)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Version info error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/versions/{version}/migration", response_model=Dict[str, Any])
async def get_migration_recommendations(version: str):
    """Get migration recommendations for an API version"""
    try:
        versioning_service = await get_api_versioning_service()

        recommendations = await versioning_service.get_migration_recommendations(
            version
        )

        if "error" in recommendations:
            raise HTTPException(status_code=404, detail=recommendations["error"])

        return recommendations

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Migration recommendations error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test-route")
async def test_route_matching(
    path: str = Query(description="Test path"),
    method: str = Query(default="GET", description="HTTP method"),
):
    """Test route matching for a given path and method"""
    try:
        gateway = await get_api_gateway()

        matching_rule = gateway.match_route(path, method)

        if matching_rule:
            return {
                "matched": True,
                "rule_id": matching_rule.rule_id,
                "target_service": matching_rule.target_service,
                "routing_strategy": matching_rule.routing_strategy.value,
                "api_version": matching_rule.api_version,
                "require_authentication": matching_rule.require_authentication,
            }
        else:
            return {
                "matched": False,
                "message": "No matching route found",
                "available_routes": [
                    {"pattern": rule.path_pattern, "methods": rule.methods}
                    for rule in gateway.routing_rules
                ],
            }

    except Exception as e:
        logger.error(f"Route testing error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
