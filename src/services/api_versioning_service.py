"""
API Versioning Service - Phase 3 Week 37
Advanced API versioning with backward compatibility management
"""

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from packaging import version
from src.services.media_cache_manager import MediaCacheManager
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api_versioning")


class VersionStrategy(Enum):
    """API versioning strategies"""

    HEADER = "header"  # Accept-Version header
    PATH = "path"  # /api/v1/endpoint
    QUERY = "query"  # ?version=1.0
    SUBDOMAIN = "subdomain"  # v1.api.example.com
    CONTENT_TYPE = "content_type"  # application/vnd.api+json;version=1


class CompatibilityLevel(Enum):
    """Backward compatibility levels"""

    BREAKING = "breaking"  # Breaking changes
    COMPATIBLE = "compatible"  # Backward compatible
    DEPRECATED = "deprecated"  # Deprecated but compatible
    EXPERIMENTAL = "experimental"  # Experimental features


class ChangeType(Enum):
    """Types of API changes"""

    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_RENAMED = "field_renamed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    ENDPOINT_ADDED = "endpoint_added"
    ENDPOINT_REMOVED = "endpoint_removed"
    ENDPOINT_RENAMED = "endpoint_renamed"
    PARAMETER_ADDED = "parameter_added"
    PARAMETER_REMOVED = "parameter_removed"
    RESPONSE_FORMAT_CHANGED = "response_format_changed"
    BEHAVIOR_CHANGED = "behavior_changed"


@dataclass
class APIVersion:
    """Represents an API version"""

    version: str
    release_date: datetime
    compatibility_level: CompatibilityLevel
    deprecation_date: Optional[datetime] = None
    sunset_date: Optional[datetime] = None

    # Version metadata
    description: str = ""
    release_notes: str = ""
    migration_guide: str = ""

    # Status
    is_active: bool = True
    is_default: bool = False
    is_deprecated: bool = False

    # Support information
    supported_until: Optional[datetime] = None
    minimum_client_version: Optional[str] = None


@dataclass
class APIChange:
    """Represents a change between API versions"""

    change_id: str
    from_version: str
    to_version: str
    change_type: ChangeType

    # Change details
    affected_endpoint: str
    field_path: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    # Impact assessment
    breaking_change: bool = False
    migration_required: bool = False
    description: str = ""

    # Transformation information
    transform_function: Optional[str] = None
    reverse_transform: Optional[str] = None


@dataclass
class VersionTransformation:
    """Defines how to transform data between versions"""

    from_version: str
    to_version: str
    transformation_id: str

    # Transformation rules
    field_mappings: Dict[str, str] = field(default_factory=dict)
    field_transforms: Dict[str, str] = field(default_factory=dict)  # Function names
    field_defaults: Dict[str, Any] = field(default_factory=dict)
    fields_to_remove: List[str] = field(default_factory=list)

    # Custom transformation
    custom_transform_function: Optional[str] = None


@dataclass
class ClientCompatibility:
    """Client compatibility information"""

    client_id: str
    client_version: str
    supported_api_versions: List[str]
    preferred_version: str

    # Compatibility matrix
    version_capabilities: Dict[str, List[str]] = field(default_factory=dict)
    required_features: List[str] = field(default_factory=list)

    # Migration status
    migration_path: List[str] = field(default_factory=list)
    last_version_used: str = ""
    migration_deadline: Optional[datetime] = None


class APIVersioningService:
    """Service for managing API versions and backward compatibility"""

    def __init__(self):
        self.cache_manager = MediaCacheManager()

        # Version registry
        self.versions: Dict[str, APIVersion] = {}
        self.changes: List[APIChange] = []
        self.transformations: Dict[Tuple[str, str], VersionTransformation] = {}

        # Client tracking
        self.client_compatibility: Dict[str, ClientCompatibility] = {}

        # Version parsing
        self.version_patterns = {
            VersionStrategy.HEADER: r"Accept-Version:\s*([0-9]+\.?[0-9]*)",
            VersionStrategy.PATH: r"/api/v([0-9]+\.?[0-9]*)/",
            VersionStrategy.QUERY: r"[?&]version=([0-9]+\.?[0-9]*)",
            VersionStrategy.CONTENT_TYPE: r"version=([0-9]+\.?[0-9]*)",
        }

        # Initialize default versions
        asyncio.create_task(self._initialize_default_versions())

        logger.info("🔄 API Versioning service initialized")

    async def _initialize_default_versions(self):
        """Initialize default API versions"""
        try:
            # Define MVidarr API versions
            default_versions = [
                APIVersion(
                    version="1.0",
                    release_date=datetime(2024, 1, 1),
                    compatibility_level=CompatibilityLevel.COMPATIBLE,
                    description="Initial MVidarr API release",
                    is_active=True,
                    is_deprecated=True,
                    deprecation_date=datetime(2024, 6, 1),
                    sunset_date=datetime(2025, 1, 1),
                ),
                APIVersion(
                    version="1.1",
                    release_date=datetime(2024, 6, 1),
                    compatibility_level=CompatibilityLevel.COMPATIBLE,
                    description="Enhanced video processing and playlist features",
                    is_active=True,
                    is_default=False,
                ),
                APIVersion(
                    version="2.0",
                    release_date=datetime(2024, 12, 1),
                    compatibility_level=CompatibilityLevel.BREAKING,
                    description="Major FastAPI migration with microservices architecture",
                    is_active=True,
                    is_default=True,
                    minimum_client_version="2.0",
                ),
            ]

            for api_version in default_versions:
                await self.register_version(api_version)

            # Add transformation rules
            await self._initialize_transformations()

            logger.info("✅ Default API versions initialized")

        except Exception as e:
            logger.error(f"Failed to initialize API versions: {e}")

    async def _initialize_transformations(self):
        """Initialize version transformation rules"""
        try:
            # v1.0 -> v1.1 transformations
            v1_0_to_v1_1 = VersionTransformation(
                from_version="1.0",
                to_version="1.1",
                transformation_id="v1_0_to_v1_1",
                field_mappings={
                    "video_url": "video_source_url",
                    "thumb_url": "thumbnail_url",
                },
                field_defaults={
                    "processing_status": "completed",
                    "metadata_version": "1.1",
                },
            )

            await self.add_transformation(v1_0_to_v1_1)

            # v1.1 -> v2.0 transformations (breaking changes)
            v1_1_to_v2_0 = VersionTransformation(
                from_version="1.1",
                to_version="2.0",
                transformation_id="v1_1_to_v2_0",
                field_mappings={
                    "id": "video_id",
                    "created": "created_at",
                    "modified": "updated_at",
                },
                field_transforms={
                    "date_format": "convert_date_format",  # Custom function
                    "status": "normalize_status",
                },
                fields_to_remove=["deprecated_field", "legacy_metadata"],
                field_defaults={"api_version": "2.0", "schema_version": "2.0"},
            )

            await self.add_transformation(v1_1_to_v2_0)

        except Exception as e:
            logger.error(f"Failed to initialize transformations: {e}")

    async def register_version(self, api_version: APIVersion) -> bool:
        """Register a new API version"""
        try:
            self.versions[api_version.version] = api_version

            # Cache version information
            await self.cache_manager.set(
                f"api_version:{api_version.version}",
                json.dumps(asdict(api_version), default=str),
                ttl=86400,
            )

            # Update versions list
            await self._update_versions_cache()

            logger.info(f"📝 API version registered: {api_version.version}")
            return True

        except Exception as e:
            logger.error(f"Failed to register API version {api_version.version}: {e}")
            return False

    async def add_transformation(self, transformation: VersionTransformation) -> bool:
        """Add version transformation rule"""
        try:
            key = (transformation.from_version, transformation.to_version)
            self.transformations[key] = transformation

            # Cache transformation
            await self.cache_manager.set(
                f"api_transform:{transformation.from_version}:{transformation.to_version}",
                json.dumps(asdict(transformation), default=str),
                ttl=86400,
            )

            logger.info(
                f"🔄 Transformation added: {transformation.from_version} -> {transformation.to_version}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add transformation: {e}")
            return False

    def extract_version(
        self,
        request_data: Dict[str, Any],
        strategy: VersionStrategy = VersionStrategy.HEADER,
    ) -> str:
        """Extract API version from request"""
        try:
            if strategy == VersionStrategy.HEADER:
                headers = request_data.get("headers", {})
                accept_version = headers.get("Accept-Version") or headers.get(
                    "accept-version"
                )
                if accept_version:
                    return accept_version

                # Check Accept header for versioned content type
                accept = headers.get("Accept") or headers.get("accept", "")
                match = re.search(
                    self.version_patterns[VersionStrategy.CONTENT_TYPE], accept
                )
                if match:
                    return match.group(1)

            elif strategy == VersionStrategy.PATH:
                path = request_data.get("path", "")
                match = re.search(self.version_patterns[VersionStrategy.PATH], path)
                if match:
                    return match.group(1)

            elif strategy == VersionStrategy.QUERY:
                query_params = request_data.get("query_params", {})
                if "version" in query_params:
                    return query_params["version"]

                # Also check in raw query string
                query_string = request_data.get("query_string", "")
                match = re.search(
                    self.version_patterns[VersionStrategy.QUERY], query_string
                )
                if match:
                    return match.group(1)

            # Return default version
            return self.get_default_version()

        except Exception as e:
            logger.error(f"Version extraction failed: {e}")
            return self.get_default_version()

    def get_default_version(self) -> str:
        """Get the default API version"""
        for version_str, api_version in self.versions.items():
            if api_version.is_default:
                return version_str

        # Fallback to highest version number
        if self.versions:
            return max(self.versions.keys(), key=lambda v: version.parse(v))

        return "1.0"

    def get_supported_versions(self) -> List[str]:
        """Get list of supported API versions"""
        return [
            ver
            for ver, api_ver in self.versions.items()
            if api_ver.is_active and not self._is_sunset(api_ver)
        ]

    def is_version_supported(self, version_str: str) -> bool:
        """Check if API version is supported"""
        if version_str not in self.versions:
            return False

        api_version = self.versions[version_str]
        return api_version.is_active and not self._is_sunset(api_version)

    def is_version_deprecated(self, version_str: str) -> bool:
        """Check if API version is deprecated"""
        if version_str not in self.versions:
            return True

        api_version = self.versions[version_str]
        return api_version.is_deprecated or (
            api_version.deprecation_date
            and api_version.deprecation_date <= datetime.utcnow()
        )

    def get_version_compatibility(
        self, from_version: str, to_version: str
    ) -> CompatibilityLevel:
        """Get compatibility level between versions"""
        if from_version == to_version:
            return CompatibilityLevel.COMPATIBLE

        try:
            from_ver = version.parse(from_version)
            to_ver = version.parse(to_version)

            # Major version change is breaking
            if from_ver.major != to_ver.major:
                return CompatibilityLevel.BREAKING

            # Minor version increase is usually compatible
            if from_ver.minor < to_ver.minor:
                return CompatibilityLevel.COMPATIBLE

            # Patch version is always compatible
            return CompatibilityLevel.COMPATIBLE

        except Exception:
            return CompatibilityLevel.BREAKING

    async def transform_data(
        self, data: Dict[str, Any], from_version: str, to_version: str
    ) -> Dict[str, Any]:
        """Transform data between API versions"""
        if from_version == to_version:
            return data

        try:
            # Look for direct transformation
            transformation_key = (from_version, to_version)
            if transformation_key in self.transformations:
                return await self._apply_transformation(
                    data, self.transformations[transformation_key]
                )

            # Look for intermediate transformations
            transformation_path = self._find_transformation_path(
                from_version, to_version
            )
            if transformation_path:
                current_data = data
                current_version = from_version

                for next_version in transformation_path:
                    if (current_version, next_version) in self.transformations:
                        transformation = self.transformations[
                            (current_version, next_version)
                        ]
                        current_data = await self._apply_transformation(
                            current_data, transformation
                        )
                        current_version = next_version

                return current_data

            # No transformation available
            logger.warning(
                f"No transformation available: {from_version} -> {to_version}"
            )
            return data

        except Exception as e:
            logger.error(f"Data transformation failed: {e}")
            return data

    async def _apply_transformation(
        self, data: Dict[str, Any], transformation: VersionTransformation
    ) -> Dict[str, Any]:
        """Apply transformation rules to data"""
        try:
            result = data.copy()

            # Apply field mappings
            for old_field, new_field in transformation.field_mappings.items():
                if old_field in result:
                    result[new_field] = result.pop(old_field)

            # Apply field transforms
            for field, transform_func in transformation.field_transforms.items():
                if field in result:
                    result[field] = await self._apply_field_transform(
                        result[field], transform_func
                    )

            # Add default values
            for field, default_value in transformation.field_defaults.items():
                if field not in result:
                    result[field] = default_value

            # Remove deprecated fields
            for field in transformation.fields_to_remove:
                result.pop(field, None)

            # Apply custom transformation function
            if transformation.custom_transform_function:
                result = await self._apply_custom_transform(
                    result, transformation.custom_transform_function
                )

            return result

        except Exception as e:
            logger.error(f"Transformation application failed: {e}")
            return data

    async def _apply_field_transform(self, value: Any, transform_func: str) -> Any:
        """Apply field-level transformation"""
        try:
            # Built-in transformations
            if transform_func == "convert_date_format":
                if isinstance(value, str):
                    # Convert from old format to ISO format
                    from datetime import datetime

                    try:
                        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                        return dt.isoformat()
                    except ValueError:
                        return value
                return value

            elif transform_func == "normalize_status":
                if isinstance(value, str):
                    # Normalize status values
                    status_mapping = {
                        "active": "enabled",
                        "inactive": "disabled",
                        "pending": "processing",
                    }
                    return status_mapping.get(value.lower(), value)
                return value

            # Add more built-in transforms as needed
            return value

        except Exception as e:
            logger.error(f"Field transform failed for {transform_func}: {e}")
            return value

    async def _apply_custom_transform(
        self, data: Dict[str, Any], func_name: str
    ) -> Dict[str, Any]:
        """Apply custom transformation function"""
        try:
            # This would typically load and execute custom transformation functions
            # For now, just return the data unchanged
            logger.info(f"Custom transform {func_name} not implemented")
            return data

        except Exception as e:
            logger.error(f"Custom transform failed: {e}")
            return data

    def _find_transformation_path(
        self, from_version: str, to_version: str
    ) -> List[str]:
        """Find transformation path between versions"""
        try:
            # Simple path finding - could be enhanced with graph algorithms
            available_versions = sorted(
                self.versions.keys(), key=lambda v: version.parse(v)
            )

            from_idx = available_versions.index(from_version)
            to_idx = available_versions.index(to_version)

            if from_idx < to_idx:
                # Forward transformation
                return available_versions[from_idx + 1 : to_idx + 1]
            else:
                # Backward transformation
                return list(reversed(available_versions[to_idx:from_idx]))

        except (ValueError, IndexError):
            return []

    def _is_sunset(self, api_version: APIVersion) -> bool:
        """Check if version has reached sunset date"""
        if not api_version.sunset_date:
            return False
        return api_version.sunset_date <= datetime.utcnow()

    async def _update_versions_cache(self):
        """Update cached versions list"""
        try:
            versions_data = {
                version_str: asdict(api_version)
                for version_str, api_version in self.versions.items()
            }

            await self.cache_manager.set(
                "api_versions:all", json.dumps(versions_data, default=str), ttl=3600
            )

        except Exception as e:
            logger.error(f"Failed to update versions cache: {e}")

    async def get_version_info(self, version_str: str) -> Optional[Dict[str, Any]]:
        """Get detailed version information"""
        if version_str not in self.versions:
            return None

        api_version = self.versions[version_str]
        return {
            "version": api_version.version,
            "release_date": api_version.release_date.isoformat(),
            "compatibility_level": api_version.compatibility_level.value,
            "is_active": api_version.is_active,
            "is_default": api_version.is_default,
            "is_deprecated": self.is_version_deprecated(version_str),
            "deprecation_date": (
                api_version.deprecation_date.isoformat()
                if api_version.deprecation_date
                else None
            ),
            "sunset_date": (
                api_version.sunset_date.isoformat() if api_version.sunset_date else None
            ),
            "description": api_version.description,
            "migration_guide": api_version.migration_guide,
        }

    async def get_migration_recommendations(
        self, current_version: str
    ) -> Dict[str, Any]:
        """Get migration recommendations for a version"""
        try:
            if current_version not in self.versions:
                return {"error": "Unknown version"}

            current = self.versions[current_version]
            recommendations = {
                "current_version": current_version,
                "is_deprecated": self.is_version_deprecated(current_version),
                "is_sunset": self._is_sunset(current),
                "supported_versions": self.get_supported_versions(),
                "recommended_version": self.get_default_version(),
                "migration_required": False,
                "migration_deadline": None,
                "breaking_changes": [],
                "migration_steps": [],
            }

            # Check if migration is required
            if current.is_deprecated or self._is_sunset(current):
                recommendations["migration_required"] = True

                if current.sunset_date:
                    recommendations["migration_deadline"] = (
                        current.sunset_date.isoformat()
                    )

            # Add migration steps
            if recommendations["migration_required"]:
                target_version = recommendations["recommended_version"]
                compatibility = self.get_version_compatibility(
                    current_version, target_version
                )

                if compatibility == CompatibilityLevel.BREAKING:
                    recommendations["breaking_changes"] = [
                        "Field names may have changed",
                        "Response formats may be different",
                        "Authentication methods may have changed",
                    ]

                recommendations["migration_steps"] = [
                    f"Review API changes from {current_version} to {target_version}",
                    "Update client code to handle new response formats",
                    "Test thoroughly before production deployment",
                    "Update API version in requests",
                ]

            return recommendations

        except Exception as e:
            logger.error(f"Failed to get migration recommendations: {e}")
            return {"error": str(e)}


# Global versioning service instance
api_versioning_service = None


async def get_api_versioning_service() -> APIVersioningService:
    """Get or create API versioning service instance"""
    global api_versioning_service
    if api_versioning_service is None:
        api_versioning_service = APIVersioningService()
    return api_versioning_service
