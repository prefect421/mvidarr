"""
Enhanced Dependency Injection Patterns - Issue 128 Advanced FastAPI Features
Advanced dependency injection patterns for scalable FastAPI applications
"""

import asyncio
import inspect
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, TypeVar

from fastapi import Depends, HTTPException, Request

from src.services.redis_service import get_redis_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.dependency_injection")

T = TypeVar("T")


class DependencyScope(Enum):
    """Dependency injection scopes"""

    SINGLETON = "singleton"
    REQUEST = "request"
    SESSION = "session"
    TRANSIENT = "transient"
    CACHED = "cached"


@dataclass
class DependencyConfig:
    """Configuration for a dependency"""

    scope: DependencyScope = DependencyScope.TRANSIENT
    cache_ttl: Optional[int] = None  # seconds
    lazy_init: bool = False
    factory_func: Optional[Callable] = None
    cleanup_func: Optional[Callable] = None


class DependencyContainer:
    """Advanced dependency injection container"""

    def __init__(self):
        self._dependencies: Dict[str, Any] = {}
        self._configs: Dict[str, DependencyConfig] = {}
        self._singletons: Dict[str, Any] = {}
        self._request_scoped: Dict[str, weakref.WeakKeyDictionary] = {}
        self._cached: Dict[str, Dict[str, Any]] = {}
        self._factories: Dict[str, Callable] = {}
        self._cleanup_callbacks: Dict[str, list] = {}

    def register(
        self,
        interface: Type[T],
        implementation: Type[T] = None,
        config: DependencyConfig = None,
        name: str = None,
    ) -> None:
        """Register a dependency with the container"""
        key = name or interface.__name__

        if implementation is None:
            implementation = interface

        config = config or DependencyConfig()

        self._dependencies[key] = implementation
        self._configs[key] = config

        if config.factory_func:
            self._factories[key] = config.factory_func

        logger.debug(f"Registered dependency '{key}' with scope {config.scope.value}")

    def get(self, interface: Type[T], request: Request = None) -> T:
        """Get a dependency instance"""
        key = interface.__name__
        config = self._configs.get(key, DependencyConfig())

        if config.scope == DependencyScope.SINGLETON:
            return self._get_singleton(key, interface)
        elif config.scope == DependencyScope.REQUEST:
            return self._get_request_scoped(key, interface, request)
        elif config.scope == DependencyScope.SESSION:
            return self._get_session_scoped(key, interface, request)
        elif config.scope == DependencyScope.CACHED:
            return self._get_cached(key, interface)
        else:  # TRANSIENT
            return self._create_instance(key, interface)

    def _get_singleton(self, key: str, interface: Type[T]) -> T:
        """Get or create singleton instance"""
        if key not in self._singletons:
            self._singletons[key] = self._create_instance(key, interface)
        return self._singletons[key]

    def _get_request_scoped(self, key: str, interface: Type[T], request: Request) -> T:
        """Get or create request-scoped instance"""
        if key not in self._request_scoped:
            self._request_scoped[key] = weakref.WeakKeyDictionary()

        request_instances = self._request_scoped[key]
        if request not in request_instances:
            request_instances[request] = self._create_instance(key, interface)

        return request_instances[request]

    def _get_session_scoped(self, key: str, interface: Type[T], request: Request) -> T:
        """Get or create session-scoped instance"""
        session_id = getattr(request.state, "session_id", "anonymous")
        session_key = f"{key}:{session_id}"

        if key not in self._cached:
            self._cached[key] = {}

        cache = self._cached[key]
        if session_key not in cache:
            cache[session_key] = self._create_instance(key, interface)

        return cache[session_key]

    def _get_cached(self, key: str, interface: Type[T]) -> T:
        """Get or create cached instance with TTL"""
        config = self._configs[key]
        now = datetime.utcnow()

        if key not in self._cached:
            self._cached[key] = {}

        cache = self._cached[key]
        cache_key = "default"

        # Check if cached instance exists and is still valid
        if cache_key in cache:
            cached_data = cache[cache_key]
            if isinstance(cached_data, dict) and "expires_at" in cached_data:
                if now < cached_data["expires_at"]:
                    return cached_data["instance"]
                else:
                    # Expired, remove from cache
                    del cache[cache_key]

        # Create new instance with expiration
        instance = self._create_instance(key, interface)
        expires_at = now + timedelta(seconds=config.cache_ttl or 300)

        cache[cache_key] = {"instance": instance, "expires_at": expires_at}

        return instance

    def _create_instance(self, key: str, interface: Type[T]) -> T:
        """Create a new instance of the dependency"""
        try:
            implementation = self._dependencies.get(key, interface)
            config = self._configs.get(key, DependencyConfig())

            # Use factory function if available
            if key in self._factories:
                factory = self._factories[key]
                instance = factory()
            elif config.factory_func:
                instance = config.factory_func()
            else:
                # Auto-wire constructor dependencies
                instance = self._auto_wire_constructor(implementation)

            # Register cleanup callback if needed
            if config.cleanup_func:
                if key not in self._cleanup_callbacks:
                    self._cleanup_callbacks[key] = []
                self._cleanup_callbacks[key].append(config.cleanup_func)

            return instance

        except Exception as e:
            logger.error(f"Failed to create instance of '{key}': {e}")
            raise HTTPException(
                status_code=500, detail=f"Dependency injection failed: {e}"
            )

    def _auto_wire_constructor(self, cls: Type[T]) -> T:
        """Automatically wire constructor dependencies"""
        try:
            sig = inspect.signature(cls.__init__)
            kwargs = {}

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                # Get type annotation
                param_type = param.annotation
                if param_type == inspect.Parameter.empty:
                    continue

                # Try to resolve dependency
                if param_type.__name__ in self._dependencies:
                    kwargs[param_name] = self.get(param_type)
                elif param.default != inspect.Parameter.empty:
                    # Use default value
                    kwargs[param_name] = param.default

            return cls(**kwargs)

        except Exception as e:
            logger.warning(f"Auto-wiring failed for {cls.__name__}: {e}")
            # Fallback to simple instantiation
            return cls()

    def cleanup(self, scope: DependencyScope = None):
        """Cleanup dependencies in specified scope"""
        if scope == DependencyScope.SINGLETON or scope is None:
            for key, cleanup_funcs in self._cleanup_callbacks.items():
                if key in self._singletons:
                    instance = self._singletons[key]
                    for cleanup_func in cleanup_funcs:
                        try:
                            cleanup_func(instance)
                        except Exception as e:
                            logger.error(f"Cleanup failed for {key}: {e}")

            if scope == DependencyScope.SINGLETON:
                self._singletons.clear()

        if scope == DependencyScope.CACHED or scope is None:
            self._cached.clear()


# Global dependency container
container = DependencyContainer()


class ServiceRegistry:
    """Service registry for managing service instances"""

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._health_checks: Dict[str, Callable] = {}
        self._metrics: Dict[str, Dict[str, Any]] = {}

    def register_service(
        self, name: str, service_instance: Any, health_check: Callable = None
    ):
        """Register a service instance"""
        self._services[name] = service_instance
        if health_check:
            self._health_checks[name] = health_check

        self._metrics[name] = {
            "registered_at": datetime.utcnow(),
            "access_count": 0,
            "last_accessed": None,
        }

        logger.info(f"Service '{name}' registered successfully")

    def get_service(self, name: str) -> Any:
        """Get a service instance"""
        if name not in self._services:
            raise HTTPException(status_code=404, detail=f"Service '{name}' not found")

        # Update metrics
        self._metrics[name]["access_count"] += 1
        self._metrics[name]["last_accessed"] = datetime.utcnow()

        return self._services[name]

    async def health_check_all(self) -> Dict[str, bool]:
        """Perform health checks on all registered services"""
        results = {}

        for name, health_check in self._health_checks.items():
            try:
                if asyncio.iscoroutinefunction(health_check):
                    result = await health_check(self._services[name])
                else:
                    result = health_check(self._services[name])
                results[name] = bool(result)
            except Exception as e:
                logger.error(f"Health check failed for service '{name}': {e}")
                results[name] = False

        return results

    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get service usage metrics"""
        return self._metrics.copy()


# Global service registry
service_registry = ServiceRegistry()


def injectable(
    scope: DependencyScope = DependencyScope.TRANSIENT,
    cache_ttl: Optional[int] = None,
    lazy: bool = False,
):
    """Decorator to mark a class as injectable"""

    def decorator(cls):
        config = DependencyConfig(scope=scope, cache_ttl=cache_ttl, lazy_init=lazy)
        container.register(cls, config=config)
        return cls

    return decorator


def inject(dependency_type: Type[T]) -> Callable:
    """Dependency injection decorator for FastAPI endpoints"""

    def dependency():
        return container.get(dependency_type)

    return Depends(dependency)


def request_scoped_inject(dependency_type: Type[T]) -> Callable:
    """Request-scoped dependency injection"""

    def dependency(request: Request):
        return container.get(dependency_type, request)

    return Depends(dependency)


class DatabaseConnectionManager:
    """Example injectable service - Database connection manager"""

    def __init__(self):
        self.connections = {}
        self.pool_size = 10
        self.active_connections = 0

    async def get_connection(self, database: str = "default"):
        """Get database connection from pool"""
        if database not in self.connections:
            # Simulate connection creation
            self.connections[database] = f"connection_to_{database}"
            self.active_connections += 1

        return self.connections[database]

    async def close_all(self):
        """Close all database connections"""
        for conn in self.connections.values():
            # Simulate connection cleanup
            pass
        self.connections.clear()
        self.active_connections = 0

    def health_check(self) -> bool:
        """Database health check"""
        return len(self.connections) < self.pool_size


class CacheManager:
    """Example injectable service - Cache manager"""

    def __init__(self):
        self.redis_client = None
        self.local_cache = {}
        self.hit_count = 0
        self.miss_count = 0

    async def initialize(self):
        """Initialize cache connections"""
        try:
            self.redis_client = await get_redis_client()
            return True
        except Exception as e:
            logger.warning(f"Redis not available, using local cache: {e}")
            return False

    async def get(self, key: str) -> Any:
        """Get value from cache"""
        try:
            if self.redis_client:
                value = await self.redis_client.get(key)
                if value:
                    self.hit_count += 1
                    return value

            # Fallback to local cache
            if key in self.local_cache:
                self.hit_count += 1
                return self.local_cache[key]

            self.miss_count += 1
            return None

        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.miss_count += 1
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set value in cache"""
        try:
            if self.redis_client:
                await self.redis_client.setex(key, ttl, value)
            else:
                self.local_cache[key] = value

            return True

        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / max(total, 1)) * 100

        return {
            "hits": self.hit_count,
            "misses": self.miss_count,
            "hit_rate": hit_rate,
            "total_requests": total,
        }


class ValidationService:
    """Example injectable service - Data validation"""

    def __init__(self):
        self.validation_rules = {}
        self.validation_count = 0
        self.error_count = 0

    def add_rule(self, field: str, validator: Callable) -> None:
        """Add validation rule for a field"""
        if field not in self.validation_rules:
            self.validation_rules[field] = []
        self.validation_rules[field].append(validator)

    def validate(self, data: Dict[str, Any]) -> Dict[str, list]:
        """Validate data against registered rules"""
        errors = {}
        self.validation_count += 1

        for field, value in data.items():
            if field in self.validation_rules:
                field_errors = []

                for validator in self.validation_rules[field]:
                    try:
                        if not validator(value):
                            field_errors.append(
                                f"Validation failed for field '{field}'"
                            )
                    except Exception as e:
                        field_errors.append(f"Validation error: {e}")

                if field_errors:
                    errors[field] = field_errors
                    self.error_count += 1

        return errors

    def get_stats(self) -> Dict[str, Any]:
        """Get validation statistics"""
        return {
            "validations_performed": self.validation_count,
            "errors_found": self.error_count,
            "error_rate": (self.error_count / max(self.validation_count, 1)) * 100,
        }


# Register default services
def register_default_services():
    """Register default injectable services"""

    # Database connection manager (singleton)
    db_config = DependencyConfig(
        scope=DependencyScope.SINGLETON,
        cleanup_func=lambda instance: asyncio.create_task(instance.close_all()),
    )
    container.register(DatabaseConnectionManager, config=db_config)

    # Cache manager (singleton with initialization)
    cache_config = DependencyConfig(
        scope=DependencyScope.SINGLETON,
        factory_func=lambda: CacheManager(),
        cleanup_func=lambda instance: setattr(instance, "redis_client", None),
    )
    container.register(CacheManager, config=cache_config)

    # Validation service (cached with 1 hour TTL)
    validation_config = DependencyConfig(scope=DependencyScope.CACHED, cache_ttl=3600)
    container.register(ValidationService, config=validation_config)

    logger.info("Default injectable services registered")


# Context managers for dependency lifecycle
@asynccontextmanager
async def dependency_context():
    """Context manager for dependency lifecycle"""
    try:
        register_default_services()
        yield container
    finally:
        container.cleanup()


# Utility functions
def get_dependency_container() -> DependencyContainer:
    """Get the global dependency container"""
    return container


def get_service_registry() -> ServiceRegistry:
    """Get the global service registry"""
    return service_registry


async def initialize_dependency_injection():
    """Initialize the dependency injection system"""
    try:
        register_default_services()

        # Initialize cache manager
        cache_manager = container.get(CacheManager)
        await cache_manager.initialize()

        # Register services with health checks
        service_registry.register_service(
            "database",
            container.get(DatabaseConnectionManager),
            lambda db: db.health_check(),
        )

        service_registry.register_service(
            "cache",
            cache_manager,
            lambda cache: True,  # Cache is always available (fallback to local)
        )

        service_registry.register_service(
            "validation", container.get(ValidationService), lambda validator: True
        )

        logger.info("Dependency injection system initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize dependency injection: {e}")
        raise


# FastAPI startup event handler
async def setup_dependency_injection(app):
    """Setup dependency injection for FastAPI app"""

    @app.on_event("startup")
    async def startup_event():
        await initialize_dependency_injection()

    @app.on_event("shutdown")
    async def shutdown_event():
        container.cleanup()
        logger.info("Dependency injection cleanup completed")

    return app


# Example usage decorators
def with_database(func):
    """Decorator to inject database connection"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        db_manager = container.get(DatabaseConnectionManager)
        connection = await db_manager.get_connection()
        kwargs["db"] = connection
        return await func(*args, **kwargs)

    return wrapper


def with_cache(func):
    """Decorator to inject cache manager"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        cache_manager = container.get(CacheManager)
        kwargs["cache"] = cache_manager
        return await func(*args, **kwargs)

    return wrapper


def with_validation(func):
    """Decorator to inject validation service"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        validator = container.get(ValidationService)
        kwargs["validator"] = validator
        return await func(*args, **kwargs)

    return wrapper
