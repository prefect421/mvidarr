"""
API Versioning System - Issue 128 Advanced FastAPI Features
Comprehensive API version management with backward compatibility
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.routing import APIRouter
from typing import Optional, Dict, Any, List, Callable
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, date
import re
import logging
from packaging import version

logger = logging.getLogger("mvidarr.api.versioning")

class APIVersionStatus(Enum):
    """API version status"""
    STABLE = "stable"
    DEPRECATED = "deprecated"
    BETA = "beta"
    ALPHA = "alpha"
    SUNSET = "sunset"

@dataclass
class APIVersionInfo:
    """API version information"""
    version: str
    status: APIVersionStatus
    release_date: date
    deprecation_date: Optional[date] = None
    sunset_date: Optional[date] = None
    description: str = ""
    breaking_changes: List[str] = None
    supported_features: List[str] = None

class APIVersionManager:
    """Manages API versioning and compatibility"""
    
    def __init__(self):
        self.versions: Dict[str, APIVersionInfo] = {}
        self.default_version = "1.0"
        self.supported_versions = set()
        
        # Initialize supported API versions
        self._initialize_versions()
        
    def _initialize_versions(self):
        """Initialize supported API versions"""
        # Version 1.0 - Original Flask migration
        self.versions["1.0"] = APIVersionInfo(
            version="1.0",
            status=APIVersionStatus.STABLE,
            release_date=date(2024, 12, 1),
            description="Initial FastAPI migration - Core functionality",
            supported_features=[
                "videos_crud", "artists_crud", "playlists_basic", 
                "admin_basic", "auth_session"
            ]
        )
        
        # Version 1.1 - Enhanced features
        self.versions["1.1"] = APIVersionInfo(
            version="1.1", 
            status=APIVersionStatus.STABLE,
            release_date=date(2025, 1, 15),
            description="Enhanced playlists, advanced search, bulk operations",
            supported_features=[
                "videos_crud", "artists_crud", "playlists_advanced",
                "admin_enhanced", "auth_jwt", "bulk_operations",
                "advanced_search", "performance_monitoring"
            ]
        )
        
        # Version 2.0 - Consumer features (current development)
        self.versions["2.0"] = APIVersionInfo(
            version="2.0",
            status=APIVersionStatus.BETA,
            release_date=date(2025, 3, 1),
            description="Consumer-focused features - Mobile, smart home, performance optimization",
            supported_features=[
                "videos_crud", "artists_crud", "playlists_advanced",
                "admin_enhanced", "auth_jwt", "bulk_operations", 
                "advanced_search", "performance_monitoring",
                "mobile_api", "smart_home", "network_streaming",
                "collection_maintenance", "offline_sync"
            ],
            breaking_changes=[
                "Enhanced error response format",
                "Standardized timestamp formats (ISO 8601)",
                "Updated pagination response structure"
            ]
        )
        
        self.supported_versions = {"1.0", "1.1", "2.0"}
        self.default_version = "2.0"
    
    def get_version_info(self, version: str) -> Optional[APIVersionInfo]:
        """Get information about a specific API version"""
        return self.versions.get(version)
    
    def is_version_supported(self, version: str) -> bool:
        """Check if API version is supported"""
        return version in self.supported_versions
    
    def get_latest_version(self) -> str:
        """Get the latest stable API version"""
        stable_versions = [
            v for v in self.versions.values() 
            if v.status == APIVersionStatus.STABLE
        ]
        if stable_versions:
            return max(stable_versions, key=lambda x: version.parse(x.version)).version
        return self.default_version
    
    def get_deprecation_warnings(self, requested_version: str) -> List[str]:
        """Get deprecation warnings for a version"""
        warnings = []
        version_info = self.get_version_info(requested_version)
        
        if version_info:
            if version_info.status == APIVersionStatus.DEPRECATED:
                warnings.append(f"API version {requested_version} is deprecated")
                if version_info.sunset_date:
                    warnings.append(f"Sunset date: {version_info.sunset_date}")
            
            if version_info.status == APIVersionStatus.SUNSET:
                warnings.append(f"API version {requested_version} is sunset and will be removed")
        
        return warnings

# Global version manager instance
version_manager = APIVersionManager()

def extract_version_from_request(request: Request) -> str:
    """Extract API version from request"""
    # Priority order: 
    # 1. Header: X-API-Version
    # 2. Accept header: application/vnd.mvidarr.v1+json
    # 3. Query parameter: version
    # 4. URL path: /api/v1/
    # 5. Default version
    
    # 1. Check X-API-Version header
    api_version_header = request.headers.get("X-API-Version")
    if api_version_header:
        return api_version_header
    
    # 2. Check Accept header for versioned media type
    accept_header = request.headers.get("Accept", "")
    version_match = re.search(r'application/vnd\.mvidarr\.v(\d+(?:\.\d+)*)', accept_header)
    if version_match:
        return version_match.group(1)
    
    # 3. Check query parameter
    version_param = request.query_params.get("version")
    if version_param:
        return version_param
    
    # 4. Check URL path
    path = request.url.path
    path_match = re.search(r'/api/v(\d+(?:\.\d+)*)', path)
    if path_match:
        return path_match.group(1)
    
    # 5. Return default version
    return version_manager.default_version

def get_api_version(request: Request = None) -> str:
    """Dependency to get API version from request"""
    if request is None:
        return version_manager.default_version
    
    requested_version = extract_version_from_request(request)
    
    # Validate version is supported
    if not version_manager.is_version_supported(requested_version):
        available_versions = list(version_manager.supported_versions)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_api_version",
                "message": f"API version '{requested_version}' is not supported",
                "supported_versions": available_versions,
                "latest_version": version_manager.get_latest_version()
            }
        )
    
    return requested_version

def version_dependency(min_version: str = None, max_version: str = None):
    """Create version dependency with constraints"""
    def _version_check(api_version: str = Depends(get_api_version)) -> str:
        parsed_version = version.parse(api_version)
        
        if min_version:
            if parsed_version < version.parse(min_version):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "version_too_old",
                        "message": f"API version {api_version} is too old. Minimum required: {min_version}",
                        "required_version": min_version
                    }
                )
        
        if max_version:
            if parsed_version > version.parse(max_version):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "version_too_new", 
                        "message": f"API version {api_version} is too new. Maximum supported: {max_version}",
                        "max_version": max_version
                    }
                )
        
        return api_version
    
    return _version_check

def add_version_headers(response, api_version: str):
    """Add version-related headers to response"""
    response.headers["X-API-Version"] = api_version
    response.headers["X-API-Latest-Version"] = version_manager.get_latest_version()
    
    # Add deprecation warnings if applicable
    warnings = version_manager.get_deprecation_warnings(api_version)
    if warnings:
        response.headers["Warning"] = "; ".join(warnings)
        response.headers["Sunset"] = version_manager.get_version_info(api_version).sunset_date.isoformat() if version_manager.get_version_info(api_version).sunset_date else ""

class VersionedRouter:
    """Router that supports API versioning"""
    
    def __init__(self, prefix: str = ""):
        self.routers: Dict[str, APIRouter] = {}
        self.prefix = prefix
        
    def add_version(self, version: str, router: APIRouter):
        """Add a versioned router"""
        self.routers[version] = router
    
    def get_router(self, version: str) -> Optional[APIRouter]:
        """Get router for specific version"""
        return self.routers.get(version)
    
    def get_all_routers(self) -> Dict[str, APIRouter]:
        """Get all versioned routers"""
        return self.routers.copy()

def create_versioned_endpoint(func: Callable, versions: List[str] = None):
    """Decorator to create version-specific endpoints"""
    if versions is None:
        versions = list(version_manager.supported_versions)
    
    def wrapper(*args, **kwargs):
        # Extract version from request context
        request = kwargs.get('request')
        if request:
            api_version = extract_version_from_request(request)
            if api_version not in versions:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "version_not_supported_for_endpoint",
                        "message": f"This endpoint doesn't support API version {api_version}",
                        "supported_versions": versions
                    }
                )
        
        return func(*args, **kwargs)
    
    return wrapper

def version_specific_response(data: Any, api_version: str) -> Dict[str, Any]:
    """Transform response data based on API version"""
    
    if api_version == "1.0":
        # Legacy format - simple response
        return data if isinstance(data, dict) else {"data": data}
    
    elif api_version == "1.1":
        # Enhanced format with metadata
        return {
            "data": data,
            "api_version": api_version,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    elif api_version == "2.0":
        # Modern format with full metadata
        return {
            "data": data,
            "meta": {
                "api_version": api_version,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "response_time": None,  # Would be filled by middleware
                "pagination": None      # Would be filled if applicable
            }
        }
    
    # Default to latest format
    return {
        "data": data,
        "meta": {
            "api_version": api_version,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    }

# API Version info endpoints
def create_version_info_router() -> APIRouter:
    """Create router for API version information"""
    router = APIRouter(prefix="/api/version", tags=["API Version"])
    
    @router.get("/info", response_model=Dict[str, Any])
    async def get_version_info(api_version: str = Depends(get_api_version)):
        """Get current API version information"""
        version_info = version_manager.get_version_info(api_version)
        
        if not version_info:
            raise HTTPException(status_code=404, detail="Version information not found")
        
        return {
            "version": version_info.version,
            "status": version_info.status.value,
            "release_date": version_info.release_date.isoformat(),
            "description": version_info.description,
            "supported_features": version_info.supported_features or [],
            "breaking_changes": version_info.breaking_changes or [],
            "deprecation_date": version_info.deprecation_date.isoformat() if version_info.deprecation_date else None,
            "sunset_date": version_info.sunset_date.isoformat() if version_info.sunset_date else None
        }
    
    @router.get("/supported", response_model=Dict[str, Any])
    async def get_supported_versions():
        """Get all supported API versions"""
        versions_info = {}
        
        for version_str, version_info in version_manager.versions.items():
            if version_str in version_manager.supported_versions:
                versions_info[version_str] = {
                    "status": version_info.status.value,
                    "release_date": version_info.release_date.isoformat(),
                    "description": version_info.description,
                    "is_default": version_str == version_manager.default_version
                }
        
        return {
            "supported_versions": versions_info,
            "default_version": version_manager.default_version,
            "latest_version": version_manager.get_latest_version()
        }
    
    return router

def apply_version_compatibility_middleware(app: FastAPI):
    """Apply middleware for version compatibility handling"""
    
    @app.middleware("http")
    async def version_compatibility_middleware(request: Request, call_next):
        # Extract and validate API version
        try:
            api_version = extract_version_from_request(request)
            
            # Add version to request state for access in endpoints
            request.state.api_version = api_version
            
            # Process request
            response = await call_next(request)
            
            # Add version headers
            add_version_headers(response, api_version)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Version compatibility middleware error: {e}")
            # Continue with default version
            request.state.api_version = version_manager.default_version
            response = await call_next(request)
            add_version_headers(response, version_manager.default_version)
            return response
    
    return app

# Backward compatibility helpers
def legacy_response_format(data: Any, api_version: str) -> Any:
    """Convert response to legacy format for older API versions"""
    if api_version == "1.0":
        # Remove newer fields that didn't exist in v1.0
        if isinstance(data, dict):
            legacy_data = data.copy()
            # Remove v2.0+ fields
            legacy_data.pop('smart_home_support', None)
            legacy_data.pop('mobile_optimization', None)
            legacy_data.pop('performance_metrics', None)
            return legacy_data
    
    return data

def feature_availability_check(feature: str, api_version: str) -> bool:
    """Check if a feature is available in the requested API version"""
    version_info = version_manager.get_version_info(api_version)
    if version_info and version_info.supported_features:
        return feature in version_info.supported_features
    return False

def require_feature(feature: str):
    """Decorator to require a specific feature for an endpoint"""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            request = kwargs.get('request')
            if request and hasattr(request.state, 'api_version'):
                api_version = request.state.api_version
                if not feature_availability_check(feature, api_version):
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "feature_not_available",
                            "message": f"Feature '{feature}' is not available in API version {api_version}",
                            "required_version": "2.0"
                        }
                    )
            return func(*args, **kwargs)
        return wrapper
    return decorator