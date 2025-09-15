"""
Centralized Pydantic Models for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

This module provides a centralized, well-organized collection of Pydantic models
for all FastAPI endpoints, eliminating duplication and ensuring consistent validation.
"""

from .admin import (
    AuditLogResponse,
    DashboardResponse,
    SystemHealthResponse,
    SystemStatusResponse,
    UserCreateRequest,
    UserResponse,
    UserRoleUpdateRequest,
    UserUpdateRequest,
)
from .ai import (
    BatchAnalysisRequest,
    BatchAnalysisResponse,
    ContentAnalysisRequest,
    ContentAnalysisResponse,
    RecommendationRequest,
    RecommendationResponse,
    TaggingRequest,
    TaggingResponse,
)
from .artist import (
    ArtistBulkRequest,
    ArtistCreateRequest,
    ArtistIMVDbImportRequest,
    ArtistResponse,
    ArtistSearchRequest,
    ArtistStatsResponse,
    ArtistUpdateRequest,
)
from .auth import (
    CredentialsRequest,
    LoginRequest,
    LoginResponse,
    OAuth2CallbackRequest,
    TokenResponse,
    UserSessionResponse,
)

# Base classes and mixins
from .base import (
    BaseRequest,
    BaseResponse,
    BulkOperationRequest,
    BulkOperationResponse,
    ErrorResponse,
    PaginationRequest,
    PaginationResponse,
    TaskStatusResponse,
    TaskSubmissionResponse,
)

# Common shared models
from .common import (
    FileUploadResponse,
    IdRequest,
    SearchFilters,
    SortOptions,
    StatusUpdateRequest,
    ThumbnailSearchRequest,
)
from .health import (
    DatabaseHealthResponse,
    DetailedHealthResponse,
    HealthResponse,
    ServiceHealthResponse,
    VersionInfoResponse,
)
from .jobs import (
    JobCancellationRequest,
    JobListResponse,
    JobProgressResponse,
    JobRequest,
    JobResponse,
    JobStatusUpdateRequest,
)
from .media import (
    BulkMediaRequest,
    BulkMediaResponse,
    VideoConversionRequest,
    VideoConversionResponse,
    VideoMetadataExtractionRequest,
    VideoMetadataResponse,
    VideoValidationRequest,
    VideoValidationResponse,
)
from .playlist import (
    DynamicPlaylistRequest,
    PlaylistAddVideoRequest,
    PlaylistCreateRequest,
    PlaylistEntryResponse,
    PlaylistFilterUpdateRequest,
    PlaylistReorderRequest,
    PlaylistResponse,
    PlaylistUpdateRequest,
)
from .settings import (
    AllSettingsResponse,
    BulkSettingsUpdateRequest,
    DatabaseConfigResponse,
    SchedulerStatusResponse,
    SettingResponse,
    SettingUpdateRequest,
)

# Domain-specific models
from .video import (
    VideoBulkDeleteRequest,
    VideoBulkDownloadRequest,
    VideoBulkStatusUpdateRequest,
    VideoCreateRequest,
    VideoDownloadRequest,
    VideoResponse,
    VideoSearchRequest,
    VideoStreamingResponse,
    VideoUpdateRequest,
)

__all__ = [
    # Base classes
    "BaseRequest",
    "BaseResponse",
    "PaginationRequest",
    "PaginationResponse",
    "BulkOperationRequest",
    "BulkOperationResponse",
    "TaskSubmissionResponse",
    "TaskStatusResponse",
    "ErrorResponse",
    # Common models
    "IdRequest",
    "StatusUpdateRequest",
    "ThumbnailSearchRequest",
    "FileUploadResponse",
    "SearchFilters",
    "SortOptions",
    # Video models
    "VideoResponse",
    "VideoCreateRequest",
    "VideoUpdateRequest",
    "VideoSearchRequest",
    "VideoBulkDeleteRequest",
    "VideoBulkDownloadRequest",
    "VideoBulkStatusUpdateRequest",
    "VideoDownloadRequest",
    "VideoStreamingResponse",
    # Artist models
    "ArtistResponse",
    "ArtistCreateRequest",
    "ArtistUpdateRequest",
    "ArtistSearchRequest",
    "ArtistBulkRequest",
    "ArtistIMVDbImportRequest",
    "ArtistStatsResponse",
    # Playlist models
    "PlaylistResponse",
    "PlaylistEntryResponse",
    "PlaylistCreateRequest",
    "PlaylistUpdateRequest",
    "PlaylistAddVideoRequest",
    "PlaylistReorderRequest",
    "DynamicPlaylistRequest",
    "PlaylistFilterUpdateRequest",
    # Auth models
    "LoginRequest",
    "LoginResponse",
    "CredentialsRequest",
    "UserSessionResponse",
    "TokenResponse",
    "OAuth2CallbackRequest",
    # Admin models
    "UserResponse",
    "UserCreateRequest",
    "UserUpdateRequest",
    "UserRoleUpdateRequest",
    "SystemStatusResponse",
    "DashboardResponse",
    "AuditLogResponse",
    "SystemHealthResponse",
    # Settings models
    "SettingResponse",
    "SettingUpdateRequest",
    "BulkSettingsUpdateRequest",
    "AllSettingsResponse",
    "SchedulerStatusResponse",
    "DatabaseConfigResponse",
    # Job models
    "JobRequest",
    "JobResponse",
    "JobProgressResponse",
    "JobListResponse",
    "JobStatusUpdateRequest",
    "JobCancellationRequest",
    # Media models
    "VideoMetadataExtractionRequest",
    "VideoMetadataResponse",
    "VideoConversionRequest",
    "VideoConversionResponse",
    "VideoValidationRequest",
    "VideoValidationResponse",
    "BulkMediaRequest",
    "BulkMediaResponse",
    # AI models
    "ContentAnalysisRequest",
    "ContentAnalysisResponse",
    "TaggingRequest",
    "TaggingResponse",
    "BatchAnalysisRequest",
    "BatchAnalysisResponse",
    "RecommendationRequest",
    "RecommendationResponse",
    # Health models
    "HealthResponse",
    "DetailedHealthResponse",
    "ServiceHealthResponse",
    "DatabaseHealthResponse",
    "VersionInfoResponse",
]
