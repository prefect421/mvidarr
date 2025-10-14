"""
Import/Export Data Models for MVidarr 0.9.7 - Issue #76
Comprehensive data portability and backup management system.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from src.database.connection import Base


class ExportFormat(Enum):
    """Supported export formats"""

    JSON = "json"
    CSV = "csv"
    XML = "xml"
    YAML = "yaml"


class ExportType(Enum):
    """Types of exports"""

    FULL_LIBRARY = "full_library"
    ARTISTS_ONLY = "artists_only"
    VIDEOS_ONLY = "videos_only"
    PLAYLISTS_ONLY = "playlists_only"
    SETTINGS_ONLY = "settings_only"
    CUSTOM_SELECTION = "custom_selection"


class ImportMode(Enum):
    """Import operation modes"""

    REPLACE_ALL = "replace_all"  # Replace entire database
    MERGE_UPDATE = "merge_update"  # Merge with existing data, update conflicts
    MERGE_SKIP = "merge_skip"  # Merge with existing data, skip conflicts
    APPEND_ONLY = "append_only"  # Only add new records


class ProcessingStatus(Enum):
    """Status of import/export operations"""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationLevel(Enum):
    """Import validation levels"""

    STRICT = "strict"  # Fail on any validation error
    MODERATE = "moderate"  # Fix minor issues, fail on major ones
    PERMISSIVE = "permissive"  # Auto-fix as many issues as possible


@dataclass
class ExportOptions:
    """Configuration options for export operations"""

    format: ExportFormat = ExportFormat.JSON
    export_type: ExportType = ExportType.FULL_LIBRARY
    include_file_paths: bool = False  # Include local file paths
    include_thumbnails: bool = True  # Include thumbnail data
    include_metadata: bool = True  # Include extended metadata
    include_user_data: bool = False  # Include user accounts (security sensitive)
    include_sessions: bool = False  # Include active sessions (typically false)
    include_cache_data: bool = False  # Include search cache and analytics
    include_temporary_data: bool = False  # Include task queues, progress data
    anonymize_users: bool = False  # Remove personal user information
    compression_enabled: bool = True  # Compress export file
    compression_level: int = 6  # 1-9, higher = better compression
    chunk_size: int = 1000  # Records per chunk for streaming
    date_range_start: Optional[datetime] = None  # Filter by creation date
    date_range_end: Optional[datetime] = None
    artist_filter: Optional[List[int]] = None  # Export specific artists only
    playlist_filter: Optional[List[int]] = None  # Export specific playlists only
    status_filter: Optional[List[str]] = None  # Filter videos by status
    encrypt_output: bool = False  # Encrypt the export file
    encryption_key: Optional[str] = None  # Encryption key for output


@dataclass
class ImportOptions:
    """Configuration options for import operations"""

    mode: ImportMode = ImportMode.MERGE_UPDATE
    validation_level: ValidationLevel = ValidationLevel.MODERATE
    overwrite_duplicates: bool = False  # Overwrite existing records with same ID
    update_existing: bool = True  # Update existing records with newer data
    skip_invalid_records: bool = True  # Skip records that fail validation
    create_missing_artists: bool = True  # Auto-create artists for videos
    preserve_ids: bool = False  # Keep original IDs (may cause conflicts)
    sanitize_file_paths: bool = True  # Clean and validate file paths
    validate_external_ids: bool = True  # Verify external service IDs
    batch_size: int = 100  # Records per batch
    max_errors: int = 50  # Maximum validation errors before aborting
    backup_before_import: bool = True  # Create backup before importing
    dry_run: bool = False  # Validate only, don't import data
    progress_callback: Optional[Any] = None  # Progress reporting function


@dataclass
class ValidationError:
    """Single validation error record"""

    record_type: str
    record_id: Optional[str]
    field_name: str
    error_code: str
    error_message: str
    suggested_fix: Optional[str] = None
    severity: str = "error"  # error, warning, info


@dataclass
class ValidationResult:
    """Result of import data validation"""

    is_valid: bool
    total_records: int
    valid_records: int
    invalid_records: int
    warnings_count: int
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    processing_time: float = 0.0


@dataclass
class ProcessingProgress:
    """Progress tracking for import/export operations"""

    current_phase: str  # parsing, validation, processing, cleanup
    total_phases: int
    current_phase_progress: float  # 0.0 to 100.0
    overall_progress: float  # 0.0 to 100.0
    records_processed: int
    total_records: int
    records_per_second: float
    estimated_time_remaining: Optional[int] = None  # seconds
    current_record_type: Optional[str] = None
    status_message: str = ""
    warnings_count: int = 0
    errors_count: int = 0


class ExportOperation(Base):
    """Track export operations"""

    __tablename__ = "export_operations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    operation_name = Column(String(255), nullable=False)
    export_type = Column(SQLEnum(ExportType), nullable=False)
    export_format = Column(SQLEnum(ExportFormat), nullable=False)
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PENDING)

    # Export configuration
    export_options = Column(JSON, nullable=True)  # Serialized ExportOptions

    # File information
    output_filename = Column(String(255), nullable=True)
    output_size_bytes = Column(Integer, nullable=True)
    output_compressed = Column(Boolean, default=False)
    output_encrypted = Column(Boolean, default=False)

    # Progress tracking
    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    progress_percentage = Column(Integer, default=0)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_completion = Column(DateTime, nullable=True)

    # Results
    result_data = Column(JSON, nullable=True)  # Export statistics
    error_log = Column(JSON, nullable=True)  # List of errors

    # Relationships
    user = relationship("User", backref="export_operations")

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "operation_name": self.operation_name,
            "export_type": self.export_type.value if self.export_type else None,
            "export_format": self.export_format.value if self.export_format else None,
            "status": self.status.value if self.status else None,
            "progress_percentage": self.progress_percentage,
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "output_filename": self.output_filename,
            "output_size_bytes": self.output_size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "result_data": self.result_data,
            "error_count": len(self.error_log) if self.error_log else 0,
        }


class ImportOperation(Base):
    """Track import operations"""

    __tablename__ = "import_operations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    operation_name = Column(String(255), nullable=False)
    import_mode = Column(SQLEnum(ImportMode), nullable=False)
    validation_level = Column(SQLEnum(ValidationLevel), nullable=False)
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.PENDING)

    # Import configuration
    import_options = Column(JSON, nullable=True)  # Serialized ImportOptions

    # Source file information
    source_filename = Column(String(255), nullable=False)
    source_size_bytes = Column(Integer, nullable=True)
    source_format = Column(SQLEnum(ExportFormat), nullable=True)
    source_encrypted = Column(Boolean, default=False)

    # Validation results
    validation_data = Column(JSON, nullable=True)  # Serialized ValidationResult

    # Progress tracking
    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    successful_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)
    progress_percentage = Column(Integer, default=0)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_completion = Column(DateTime, nullable=True)

    # Results
    result_data = Column(JSON, nullable=True)  # Import statistics
    error_log = Column(JSON, nullable=True)  # List of errors and warnings

    # Backup information (if backup was created before import)
    backup_filename = Column(String(255), nullable=True)
    backup_created = Column(Boolean, default=False)

    # Relationships
    user = relationship("User", backref="import_operations")

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "operation_name": self.operation_name,
            "import_mode": self.import_mode.value if self.import_mode else None,
            "validation_level": (
                self.validation_level.value if self.validation_level else None
            ),
            "status": self.status.value if self.status else None,
            "progress_percentage": self.progress_percentage,
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "successful_records": self.successful_records,
            "failed_records": self.failed_records,
            "source_filename": self.source_filename,
            "source_size_bytes": self.source_size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "validation_data": self.validation_data,
            "backup_created": self.backup_created,
            "error_count": len(self.error_log) if self.error_log else 0,
        }


class BackupSchedule(Base):
    """Automated backup scheduling configuration"""

    __tablename__ = "backup_schedules"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Schedule configuration
    enabled = Column(Boolean, default=True)
    frequency = Column(String(50), nullable=False)  # daily, weekly, monthly, custom
    schedule_expression = Column(
        String(255), nullable=True
    )  # Cron expression for custom

    # Backup configuration
    export_options = Column(JSON, nullable=True)  # Serialized ExportOptions
    retention_days = Column(Integer, default=30)  # Keep backups for N days
    max_backups = Column(Integer, default=10)  # Maximum number of backups to keep

    # Storage configuration
    backup_directory = Column(String(500), nullable=False)
    filename_template = Column(String(255), default="mvidarr_backup_{timestamp}.json")

    # Status tracking
    last_backup_at = Column(DateTime, nullable=True)
    last_backup_status = Column(String(50), nullable=True)  # success, failed, skipped
    last_backup_filename = Column(String(255), nullable=True)
    last_backup_size = Column(Integer, nullable=True)
    next_scheduled_at = Column(DateTime, nullable=True)

    # Error handling
    consecutive_failures = Column(Integer, default=0)
    max_consecutive_failures = Column(Integer, default=3)
    notify_on_failure = Column(Boolean, default=True)
    notification_email = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="backup_schedules")

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "frequency": self.frequency,
            "schedule_expression": self.schedule_expression,
            "retention_days": self.retention_days,
            "max_backups": self.max_backups,
            "backup_directory": self.backup_directory,
            "filename_template": self.filename_template,
            "last_backup_at": (
                self.last_backup_at.isoformat() if self.last_backup_at else None
            ),
            "last_backup_status": self.last_backup_status,
            "next_scheduled_at": (
                self.next_scheduled_at.isoformat() if self.next_scheduled_at else None
            ),
            "consecutive_failures": self.consecutive_failures,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# Data export/import schema definitions using dataclasses


@dataclass
class ExportedArtist:
    """Exportable artist data"""

    id: int
    name: str
    imvdb_id: Optional[str] = None
    spotify_id: Optional[str] = None
    lastfm_name: Optional[str] = None
    thumbnail_url: Optional[str] = None
    auto_download: bool = False
    monitored: bool = False
    keywords: Optional[List[str]] = None
    folder_path: Optional[str] = None
    genres: Optional[List[str]] = None
    source: Optional[str] = None
    imvdb_metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Statistics (computed fields)
    video_count: int = 0
    downloaded_count: int = 0


@dataclass
class ExportedVideo:
    """Exportable video data"""

    id: int
    artist_id: int
    title: str
    imvdb_id: Optional[str] = None
    youtube_id: Optional[str] = None
    youtube_url: Optional[str] = None
    url: Optional[str] = None
    playlist_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None
    year: Optional[int] = None
    release_date: Optional[str] = None
    description: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    genres: Optional[List[str]] = None
    directors: Optional[List[str]] = None
    producers: Optional[List[str]] = None
    status: str = "WANTED"
    quality: Optional[str] = None
    video_metadata: Optional[Dict[str, Any]] = None
    imvdb_metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # FFmpeg metadata (extracted from video_metadata)
    width: Optional[int] = None
    height: Optional[int] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    fps: Optional[float] = None
    bitrate: Optional[int] = None
    ffmpeg_extracted: bool = False

    # File information (optional)
    local_path: Optional[str] = None
    file_size: Optional[int] = None


@dataclass
class ExportedPlaylist:
    """Exportable playlist data"""

    id: int
    name: str
    user_id: int
    description: Optional[str] = None
    is_public: bool = False
    is_featured: bool = False
    total_duration: Optional[int] = None
    video_count: int = 0
    playlist_metadata: Optional[Dict[str, Any]] = None
    thumbnail_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Playlist entries
    entries: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExportedSetting:
    """Exportable application setting"""

    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class ExportManifest:
    """Export file metadata and manifest"""

    export_version: str = "1.0"
    mvidarr_version: str = "0.9.7"
    export_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    export_type: str = "full_library"
    export_format: str = "json"
    compression_enabled: bool = False
    encryption_enabled: bool = False

    # Data counts
    total_records: int = 0
    artists_count: int = 0
    videos_count: int = 0
    playlists_count: int = 0
    settings_count: int = 0

    # Export options used
    includes_file_paths: bool = False
    includes_thumbnails: bool = True
    includes_metadata: bool = True
    includes_user_data: bool = False
    anonymized_users: bool = False

    # Data integrity
    checksum: Optional[str] = None
    file_size_bytes: int = 0

    # Export source
    exported_by_user: Optional[str] = None
    export_hostname: Optional[str] = None


@dataclass
class ExportData:
    """Complete export data structure"""

    manifest: ExportManifest
    artists: List[ExportedArtist] = field(default_factory=list)
    videos: List[ExportedVideo] = field(default_factory=list)
    playlists: List[ExportedPlaylist] = field(default_factory=list)
    settings: List[ExportedSetting] = field(default_factory=list)
    blacklist: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExportData":
        """Create from dictionary"""
        manifest_data = data.get("manifest", {})
        manifest = ExportManifest(**manifest_data)

        artists = [ExportedArtist(**artist) for artist in data.get("artists", [])]
        videos = [ExportedVideo(**video) for video in data.get("videos", [])]
        playlists = [
            ExportedPlaylist(**playlist) for playlist in data.get("playlists", [])
        ]
        settings = [ExportedSetting(**setting) for setting in data.get("settings", [])]
        blacklist = data.get("blacklist", [])

        return cls(
            manifest=manifest,
            artists=artists,
            videos=videos,
            playlists=playlists,
            settings=settings,
            blacklist=blacklist,
        )
