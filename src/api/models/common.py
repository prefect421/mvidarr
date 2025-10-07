"""
Common Shared Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Provides commonly-used models that are shared across multiple API endpoints.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, HttpUrl, field_validator, validator

from .base import BaseRequest, BaseResponse, SortOrder


class IdRequest(BaseRequest):
    """Simple request containing a single ID"""

    id: int = Field(..., ge=1, description="Unique identifier")


class StatusUpdateRequest(BaseRequest):
    """Request to update an entity's status"""

    status: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="New status value (alphanumeric, underscore, hyphen only)",
    )


class ThumbnailSearchRequest(BaseRequest):
    """Request to search for thumbnails from external sources"""

    query: Optional[str] = Field(
        None, min_length=1, max_length=200, description="Search query for thumbnail"
    )
    source: str = Field(
        default="auto",
        pattern="^(auto|youtube|imvdb|google|tmdb|local)$",
        description="Thumbnail source: auto, youtube, imvdb, google, tmdb, or local",
    )
    size: Optional[str] = Field(
        None,
        pattern="^(small|medium|large|original)$",
        description="Preferred thumbnail size",
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of thumbnail results (1-50)",
    )


class FileUploadResponse(BaseResponse):
    """Response for file upload operations"""

    file_id: Optional[str] = Field(
        None, description="Unique identifier for uploaded file"
    )
    file_path: str = Field(description="Path where file was saved")
    file_size: int = Field(ge=0, description="Size of uploaded file in bytes")
    mime_type: Optional[str] = Field(None, description="Detected MIME type of file")
    original_filename: str = Field(
        description="Original filename as provided by client"
    )
    checksum: Optional[str] = Field(None, description="File checksum (SHA256)")

    @validator("file_path")
    def validate_file_path(cls, v):
        """Ensure file path exists and is accessible"""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"File path does not exist: {v}")
        return str(path.absolute())


class SearchFilters(BaseModel):
    """Common search filter options"""

    query: Optional[str] = Field(
        None, min_length=1, max_length=200, description="Text search query"
    )
    tags: Optional[List[str]] = Field(
        None, max_items=20, description="Filter by tags (max 20)"
    )
    date_from: Optional[datetime] = Field(
        None, description="Filter items created after this date"
    )
    date_to: Optional[datetime] = Field(
        None, description="Filter items created before this date"
    )
    status: Optional[str] = Field(
        None, pattern="^[a-zA-Z0-9_-]+$", description="Filter by status"
    )

    @validator("date_to")
    def validate_date_range(cls, v, values):
        """Ensure date_to is after date_from"""
        if v and "date_from" in values and values["date_from"]:
            if v <= values["date_from"]:
                raise ValueError("date_to must be after date_from")
        return v

    @validator("tags")
    def validate_tags(cls, v):
        """Ensure tags are valid"""
        if v:
            for tag in v:
                if not tag or not tag.strip():
                    raise ValueError("Tags cannot be empty or whitespace-only")
                if len(tag) > 50:
                    raise ValueError("Individual tags cannot exceed 50 characters")
            return [tag.strip().lower() for tag in v]
        return v


class SortOptions(BaseModel):
    """Common sorting options"""

    sort_by: str = Field(
        default="created_at",
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_.]+$",
        description="Field name to sort by",
    )
    sort_order: SortOrder = Field(
        default=SortOrder.DESC, description="Sort order: 'asc' or 'desc'"
    )


class UrlValidationMixin(BaseModel):
    """Mixin for validating URLs in models"""

    @field_validator("*", mode="before")
    @classmethod
    def validate_urls(cls, v, info):
        """Validate URL fields"""
        if info.field_name and (
            info.field_name.endswith("_url") or info.field_name == "url"
        ):
            if v and isinstance(v, str):
                if not v.startswith(("http://", "https://", "ftp://")):
                    raise ValueError(f"Invalid URL format: {v}")
                # Additional URL validation can be added here
        return v


class TimestampMixin(BaseModel):
    """Mixin for models with timestamp fields"""

    created_at: Optional[datetime] = Field(
        None, description="When the item was created"
    )
    updated_at: Optional[datetime] = Field(
        None, description="When the item was last updated"
    )

    model_config = {
        "json_encoders": {datetime: lambda dt: dt.isoformat() if dt else None}
    }


class MetadataMixin(BaseModel):
    """Mixin for models that include metadata"""

    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata as key-value pairs"
    )

    @validator("metadata")
    def validate_metadata(cls, v):
        """Ensure metadata values are JSON serializable"""
        if v:
            try:
                import json

                json.dumps(v)  # Test serialization
                return v
            except (TypeError, ValueError):
                raise ValueError("Metadata must contain JSON-serializable values")
        return v


class GenresMixin(BaseModel):
    """Mixin for models with genre fields"""

    genres: Optional[List[str]] = Field(
        None, max_items=20, description="List of genres (max 20)"
    )

    @validator("genres")
    def validate_genres(cls, v):
        """Ensure genres are valid"""
        if v:
            cleaned_genres = []
            for genre in v:
                if not genre or not genre.strip():
                    continue
                clean_genre = genre.strip().title()
                if len(clean_genre) > 50:
                    raise ValueError("Genre names cannot exceed 50 characters")
                if clean_genre not in cleaned_genres:
                    cleaned_genres.append(clean_genre)
            return cleaned_genres[:20]  # Limit to 20 genres
        return v


class PriorityRequest(BaseRequest):
    """Request with priority field"""

    priority: int = Field(
        default=1, ge=1, le=10, description="Priority level (1=lowest, 10=highest)"
    )


class BulkDeleteRequest(BaseRequest):
    """Standardized bulk delete request"""

    ids: List[int] = Field(
        ...,
        min_items=1,
        max_items=1000,
        description="List of IDs to delete (1-1000 items)",
    )
    force: bool = Field(
        default=False, description="Force deletion even if item is in use"
    )

    @validator("ids")
    def validate_unique_ids(cls, v):
        """Ensure IDs are positive and unique"""
        if not all(isinstance(id_, int) and id_ > 0 for id_ in v):
            raise ValueError("All IDs must be positive integers")
        return list(dict.fromkeys(v))  # Remove duplicates while preserving order


class HealthCheckResponse(BaseResponse):
    """Standard health check response"""

    service: str = Field(description="Name of the service")
    version: str = Field(description="Service version")
    uptime: float = Field(ge=0, description="Service uptime in seconds")
    dependencies: Dict[str, str] = Field(
        default_factory=dict, description="Status of service dependencies"
    )


class ConfigurationResponse(BaseResponse):
    """Response containing configuration information"""

    config: Dict[str, Any] = Field(description="Configuration key-value pairs")
    environment: str = Field(description="Current environment (dev, prod, etc.)")
    debug_mode: bool = Field(description="Whether debug mode is enabled")

    @validator("config")
    def sanitize_config(cls, v):
        """Remove sensitive configuration values from response"""
        sensitive_keys = {
            "password",
            "secret",
            "key",
            "token",
            "auth",
            "credential",
            "database_url",
            "redis_url",
            "private",
        }

        sanitized = {}
        for key, value in v.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value
        return sanitized


# Export commonly used models
__all__ = [
    "IdRequest",
    "StatusUpdateRequest",
    "ThumbnailSearchRequest",
    "FileUploadResponse",
    "SearchFilters",
    "SortOptions",
    "UrlValidationMixin",
    "TimestampMixin",
    "MetadataMixin",
    "GenresMixin",
    "PriorityRequest",
    "BulkDeleteRequest",
    "HealthCheckResponse",
    "ConfigurationResponse",
]
