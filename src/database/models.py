"""
Database models for MVidarr
"""

import secrets
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import JSON, Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import relationship, validates
from werkzeug.security import check_password_hash, generate_password_hash

from src.database.connection import Base


class VideoStatus(Enum):
    """Video status enumeration"""

    WANTED = "WANTED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"
    MONITORED = "MONITORED"  # Video is being monitored but not actively wanted


class UserRole(Enum):
    """User role enumeration"""

    ADMIN = "ADMIN"  # Full access to everything
    MANAGER = "MANAGER"  # Can manage content and users (except admins)
    USER = "USER"  # Can view and download content
    READONLY = "READONLY"  # Can only view content, no modifications


class SessionStatus(Enum):
    """Session status enumeration"""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class PlaylistType(Enum):
    """Playlist type enumeration"""

    STATIC = "STATIC"  # Traditional playlists with manually added videos
    DYNAMIC = "DYNAMIC"  # Auto-updating playlists based on filter criteria


class WizardStep(Enum):
    """Installation wizard step enumeration"""

    WELCOME = "welcome"  # Welcome screen
    ADMIN_ACCOUNT = "admin_account"  # Admin account creation
    DIRECTORIES = "directories"  # Directory configuration
    API_CONFIG = "api_config"  # API keys configuration
    VIDEO_IMPORT = "video_import"  # Initial video import
    COMPLETE = "complete"  # Wizard completion


class WizardStatus(Enum):
    """Installation wizard status enumeration"""

    NOT_STARTED = "not_started"  # Wizard has not been started
    IN_PROGRESS = "in_progress"  # Wizard is in progress
    COMPLETED = "completed"  # Wizard has been completed
    SKIPPED = "skipped"  # User skipped the wizard


class Setting(Base):
    """Application settings"""

    __tablename__ = "settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    key = Column(String(255), unique=True, nullable=False)
    value = Column(
        MEDIUMTEXT, nullable=True
    )  # Changed from Text to MEDIUMTEXT for large values (cookies, etc)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Setting(key='{self.key}', value='{self.value}')>"


class User(Base):
    """Application users"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)  # IPv6 compatible
    password_changed_at = Column(DateTime, default=datetime.utcnow)
    email_verification_token = Column(String(255), nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    two_factor_secret = Column(String(32), nullable=True)
    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    backup_codes = Column(JSON, nullable=True)  # List of backup codes
    preferences = Column(JSON, nullable=True)  # User preferences like theme, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )

    def __init__(self, username, email, password, role=UserRole.USER):
        self.username = username
        self.email = email
        self.set_password(password)
        self.role = role

    def set_password(self, password):
        """Set password hash with validation"""
        from src.utils.security import PasswordValidator

        # Validate password strength
        is_valid, errors = PasswordValidator.validate_password_strength(password)
        if not is_valid:
            raise ValueError(f"Password validation failed: {'; '.join(errors)}")

        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()

    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)

    def is_locked(self):
        """Check if user account is locked"""
        if self.locked_until is None:
            return False
        return datetime.utcnow() < self.locked_until

    def lock_account(self, duration_minutes=30):
        """Lock user account for specified duration"""
        self.locked_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        self.failed_login_attempts = 0

    def unlock_account(self):
        """Unlock user account"""
        self.locked_until = None
        self.failed_login_attempts = 0

    def increment_failed_login(self):
        """Increment failed login attempts"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.lock_account()

    def reset_failed_login(self):
        """Reset failed login attempts"""
        self.failed_login_attempts = 0

    def generate_email_verification_token(self):
        """Generate email verification token"""
        self.email_verification_token = secrets.token_urlsafe(32)
        return self.email_verification_token

    def generate_password_reset_token(self, expires_hours=1):
        """Generate password reset token"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_expires = datetime.utcnow() + timedelta(hours=expires_hours)
        return self.password_reset_token

    def verify_password_reset_token(self, token):
        """Verify password reset token"""
        if not self.password_reset_token or not self.password_reset_expires:
            return False
        if datetime.utcnow() > self.password_reset_expires:
            return False
        return self.password_reset_token == token

    def has_permission(self, required_role):
        """Check if user has required permission level"""
        role_hierarchy = {
            UserRole.READONLY: 0,
            UserRole.USER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(required_role, 0)

    def can_access_admin(self):
        """Check if user can access admin functions"""
        return self.role in [UserRole.ADMIN, UserRole.MANAGER]

    def can_modify_content(self):
        """Check if user can modify content"""
        return self.role in [UserRole.ADMIN, UserRole.MANAGER, UserRole.USER]

    def can_delete_content(self):
        """Check if user can delete content"""
        return self.role in [UserRole.ADMIN, UserRole.MANAGER]

    def can_manage_users(self):
        """Check if user can manage other users"""
        return self.role == UserRole.ADMIN

    def to_dict(self, include_sensitive=False):
        """Convert user to dictionary"""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "is_active": self.is_active,
            "is_email_verified": self.is_email_verified,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "preferences": self.preferences or {},
        }

        if include_sensitive:
            data.update(
                {
                    "failed_login_attempts": self.failed_login_attempts,
                    "is_locked": self.is_locked(),
                    "locked_until": (
                        self.locked_until.isoformat() if self.locked_until else None
                    ),
                    "last_login_ip": self.last_login_ip,
                    "two_factor_enabled": self.two_factor_enabled,
                }
            )

        return data

    def __repr__(self):
        return f"<User(username='{self.username}', role='{self.role.value}')>"


class UserSession(Base):
    """User session management"""

    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False)
    status = Column(
        SQLEnum(SessionStatus), default=SessionStatus.ACTIVE, nullable=False
    )
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    # Relationships
    user = relationship("User", back_populates="sessions")

    def __init__(self, user_id, ip_address=None, user_agent=None, expires_hours=24):
        self.user_id = user_id
        self.session_token = self.generate_session_token()
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

    @staticmethod
    def generate_session_token():
        """Generate secure session token"""
        return secrets.token_urlsafe(32)

    def is_valid(self):
        """Check if session is valid"""
        return (
            self.status == SessionStatus.ACTIVE and datetime.utcnow() < self.expires_at
        )

    def refresh(self, extend_hours=24):
        """Refresh session expiry"""
        self.last_activity = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(hours=extend_hours)

    def revoke(self):
        """Revoke session"""
        self.status = SessionStatus.REVOKED

    def expire(self):
        """Mark session as expired"""
        self.status = SessionStatus.EXPIRED

    def to_dict(self):
        """Convert session to dictionary"""
        return {
            "id": self.id,
            "session_token": self.session_token,
            "status": self.status.value,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_valid": self.is_valid(),
        }

    def __repr__(self):
        return f"<UserSession(user_id={self.user_id}, status='{self.status.value}')>"


class Artist(Base):
    """Artists being tracked"""

    __tablename__ = "artists"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    sort_name = Column(String(255), nullable=True)  # For alphabetical sorting
    imvdb_id = Column(String(100), unique=True, nullable=True)
    spotify_id = Column(String(100), nullable=True)  # Spotify artist ID
    lastfm_name = Column(String(255), nullable=True)  # Last.fm artist name
    thumbnail_url = Column(String(500), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    thumbnail_source = Column(
        String(50), nullable=True
    )  # 'imvdb', 'wikipedia', 'manual', 'generated'
    thumbnail_metadata = Column(JSON, nullable=True)  # Store sizes, upload info, etc.
    thumbnail_uploaded_at = Column(DateTime, nullable=True)  # When manually uploaded
    auto_download = Column(Boolean, default=False)
    keywords = Column(JSON, nullable=True)  # Video filtering keywords
    folder_path = Column(String(500), nullable=True)
    imvdb_metadata = Column(JSON, nullable=True)  # Additional IMVDB metadata
    genres = Column(
        JSON, nullable=True
    )  # Artist genres (automatically updated from videos)
    labels = Column(JSON, nullable=True)  # Record labels associated with the artist
    members = Column(Text, nullable=True)  # Band members (stored as text)
    # Category 2 fields - Issue #174: Fields in API but were missing from database
    biography = Column(Text, nullable=True)  # Artist biography/description
    formed_year = Column(Integer, nullable=True)  # Year the artist/band was formed
    location = Column(String(255), nullable=True)  # Artist origin location
    website = Column(String(500), nullable=True)  # Official artist website
    wikipedia_url = Column(String(500), nullable=True)  # Wikipedia article URL
    musicbrainz_id = Column(String(100), nullable=True)  # MusicBrainz identifier
    imvdb_slug = Column(String(100), nullable=True)  # IMVDb URL slug
    # Category 3 fields - Issue #174: Fields in frontend but were missing from API/database
    overview = Column(Text, nullable=True)  # Artist overview/summary
    disbanded_year = Column(Integer, nullable=True)  # Year the band disbanded
    origin_country = Column(String(100), nullable=True)  # Country of origin
    spotify_url = Column(String(500), nullable=True)  # Spotify profile URL
    youtube_url = Column(String(500), nullable=True)  # YouTube channel URL
    apple_music_url = Column(String(500), nullable=True)  # Apple Music profile URL
    twitter_url = Column(String(500), nullable=True)  # Twitter/X profile URL
    facebook_url = Column(String(500), nullable=True)  # Facebook page URL
    instagram_url = Column(String(500), nullable=True)  # Instagram profile URL
    quality_profile = Column(String(50), nullable=True)  # Quality profile for downloads
    priority = Column(Integer, nullable=True)  # Artist priority for downloads
    monitored = Column(Boolean, default=True)
    source = Column(
        String(50), nullable=True
    )  # Source: 'imvdb', 'spotify_import', 'manual', etc.
    last_discovery = Column(DateTime, nullable=True)  # Last time videos were discovered

    # Scheduler V2 fields (v0.10.1)
    discovery_interval_hours = Column(
        Integer, default=24
    )  # Per-artist discovery interval in hours
    last_download = Column(
        DateTime, nullable=True
    )  # Last time a download was triggered for this artist
    discovery_enabled = Column(
        Boolean, default=True
    )  # Can disable discovery independently of monitoring
    download_enabled = Column(
        Boolean, default=True
    )  # Can disable auto-downloads independently
    max_videos_per_discovery = Column(
        Integer, default=50
    )  # Maximum videos to discover per run for this artist
    schedule_priority = Column(
        String(20), default="medium"
    )  # Scheduling priority: 'high', 'medium', 'low'
    allowed_video_types = Column(
        JSON, nullable=True
    )  # List of allowed video types for auto-download filtering (Issue #191)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    videos = relationship(
        "Video", back_populates="artist", cascade="all, delete-orphan"
    )
    downloads = relationship(
        "Download", back_populates="artist", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_artist_name", "name"),
        Index("idx_artist_sort_name", "sort_name"),  # Migration 006
        Index("idx_artist_imvdb_id", "imvdb_id"),
        Index("idx_artist_spotify_id", "spotify_id"),
        Index("idx_artist_monitored", "monitored"),
        Index("idx_artist_source", "source"),
        # Category 2 field indexes - Issue #174
        Index("idx_artist_formed_year", "formed_year"),
        Index("idx_artist_musicbrainz_id", "musicbrainz_id"),
        Index("idx_artist_imvdb_slug", "imvdb_slug"),
        # Category 3 field indexes - Issue #174
        Index("idx_artist_origin_country", "origin_country"),
        Index("idx_artist_disbanded_year", "disbanded_year"),
        Index("idx_artist_quality_profile", "quality_profile"),
        Index("idx_artist_priority", "priority"),
        # Scheduler V2 indexes - v0.10.1
        Index("idx_artist_discovery_enabled", "discovery_enabled"),
        Index("idx_artist_download_enabled", "download_enabled"),
        Index("idx_artist_schedule_priority", "schedule_priority"),
        Index("idx_artist_last_discovery", "last_discovery"),
        Index("idx_artist_last_download", "last_download"),
        Index(
            "idx_artist_scheduler_query",
            "monitored",
            "discovery_enabled",
            "schedule_priority",
        ),  # Composite for scheduler queries
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<Artist(name='{self.name}', imvdb_id='{self.imvdb_id}')>"


class Video(Base):
    """Videos discovered for artists"""

    __tablename__ = "videos"

    id = Column(Integer, primary_key=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False)
    title = Column(String(500), nullable=False)
    imvdb_id = Column(String(100), unique=True, nullable=True)
    youtube_id = Column(String(100), nullable=True)
    youtube_url = Column(String(500), nullable=True)  # YouTube video URL
    url = Column(String(500), nullable=True)  # Video URL (YouTube, etc.)
    playlist_id = Column(
        String(100), nullable=True
    )  # YouTube playlist ID if from playlist
    playlist_position = Column(Integer, nullable=True)  # Position in playlist
    source = Column(
        String(50), nullable=True
    )  # Source: 'imvdb', 'youtube_playlist', 'manual', etc.
    thumbnail_url = Column(String(500), nullable=True)
    thumbnail_path = Column(String(500), nullable=True)
    thumbnail_source = Column(
        String(50), nullable=True
    )  # 'imvdb', 'youtube', 'manual', 'generated'
    thumbnail_metadata = Column(JSON, nullable=True)  # Store sizes, upload info, etc.
    thumbnail_uploaded_at = Column(DateTime, nullable=True)  # When manually uploaded
    local_path = Column(String(500), nullable=True)  # Path to local video file
    duration = Column(Integer, nullable=True)  # Duration in seconds
    year = Column(Integer, nullable=True)
    release_date = Column(DateTime, nullable=True)  # Video release/publish date
    description = Column(Text, nullable=True)  # Video description
    view_count = Column(Integer, nullable=True)  # View count
    like_count = Column(Integer, nullable=True)  # Like count from video platforms
    genres = Column(JSON, nullable=True)  # Video genres
    album = Column(String(500), nullable=True)  # Album name
    directors = Column(JSON, nullable=True)
    producers = Column(JSON, nullable=True)
    status = Column(SQLEnum(VideoStatus), default=VideoStatus.WANTED)
    quality = Column(String(50), nullable=True)
    video_metadata = Column(JSON, nullable=True)  # General metadata
    imvdb_metadata = Column(JSON, nullable=True)  # Full IMVDB metadata
    search_keywords = Column(Text, nullable=True)  # Keywords for matching
    discovered_date = Column(DateTime, nullable=True)  # When video was first discovered
    last_enriched = Column(
        DateTime, nullable=True
    )  # Last metadata enrichment timestamp
    lyrics = Column(Text, nullable=True)  # Song lyrics
    video_type = Column(
        String(50), nullable=True
    )  # Video type classification: official_music_video, live_performance, lyric_video, etc. (Issue #191)

    # Quality checking fields
    available_qualities = Column(JSON, nullable=True)  # Available formats from YouTube
    quality_check_date = Column(DateTime, nullable=True)  # Last quality check date
    max_available_quality = Column(
        String(50), nullable=True
    )  # Highest available quality
    quality_check_status = Column(
        String(50), nullable=True
    )  # Check status: success/failed/pending

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    artist = relationship("Artist", back_populates="videos")
    downloads = relationship(
        "Download", back_populates="video", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_video_artist_id", "artist_id"),
        Index("idx_video_imvdb_id", "imvdb_id"),
        Index("idx_video_youtube_id", "youtube_id"),
        Index("idx_video_playlist_id", "playlist_id"),
        Index("idx_video_status", "status"),
        Index("idx_video_title", "title"),
        Index("idx_video_source", "source"),
        {"extend_existing": True},
    )

    @validates("title")
    def validate_title(self, key, value):
        """Ensure title is always a string"""
        if value is None:
            return ""
        return str(value)

    def __repr__(self):
        return f"<Video(title='{self.title}', artist_id={self.artist_id}, status='{self.status}')>"


class Download(Base):
    """Download history and file tracking"""

    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=True)
    title = Column(String(500), nullable=False)
    original_url = Column(String(500), nullable=False)
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)  # Size in bytes
    download_date = Column(DateTime, default=datetime.utcnow)
    metube_id = Column(String(100), nullable=True)  # MeTube download ID
    status = Column(
        String(50), default="pending"
    )  # pending, downloading, completed, failed
    priority = Column(
        Integer, default=5
    )  # 1-10, lower is higher priority (1=highest, 10=lowest)
    progress = Column(Integer, default=0)  # Download progress percentage
    error_message = Column(Text, nullable=True)
    quality = Column(String(50), nullable=True)
    format = Column(String(50), nullable=True)
    download_metadata = Column(JSON, nullable=True)

    # Scheduler V2 retry fields (v0.10.1)
    retry_count = Column(Integer, default=0)  # Number of retry attempts
    last_attempt = Column(DateTime, nullable=True)  # Last retry attempt timestamp
    last_error = Column(Text, nullable=True)  # Last error message encountered
    next_retry_at = Column(
        DateTime, nullable=True
    )  # Scheduled time for next retry (exponential backoff)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    artist = relationship("Artist", back_populates="downloads")
    video = relationship("Video", back_populates="downloads")

    # Indexes
    __table_args__ = (
        Index("idx_download_artist_id", "artist_id"),
        Index("idx_download_video_id", "video_id"),
        Index("idx_download_status", "status"),
        Index("idx_download_priority", "priority"),
        Index("idx_download_date", "download_date"),
        Index("idx_download_metube_id", "metube_id"),
        Index(
            "idx_download_priority_status", "priority", "status"
        ),  # Composite index for queue ordering
        # Scheduler V2 indexes - v0.10.1
        Index("idx_download_retry_count", "retry_count"),
        Index("idx_download_next_retry_at", "next_retry_at"),
        Index(
            "idx_download_retry_status", "status", "retry_count", "next_retry_at"
        ),  # For finding failed downloads to retry
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<Download(title='{self.title}', status='{self.status}', artist_id={self.artist_id})>"


# User class is defined above with full authentication features


class TaskQueue(Base):
    """Background task queue"""

    __tablename__ = "task_queue"

    id = Column(Integer, primary_key=True)
    task_type = Column(String(100), nullable=False)  # artist_scan, video_download, etc.
    task_data = Column(JSON, nullable=True)
    status = Column(
        String(50), default="pending"
    )  # pending, running, completed, failed
    priority = Column(Integer, default=5)  # 1-10, lower is higher priority
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_task_status", "status"),
        Index("idx_task_priority", "priority"),
        Index("idx_task_type", "task_type"),
        Index("idx_task_created_at", "created_at"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<TaskQueue(task_type='{self.task_type}', status='{self.status}')>"


class ScheduledJob(Base):
    """Scheduled job tracking for Scheduler V2"""

    __tablename__ = "scheduled_jobs"

    id = Column(Integer, primary_key=True)
    job_type = Column(
        String(50), nullable=False
    )  # 'discovery', 'download', 'health_check'
    artist_id = Column(
        Integer, ForeignKey("artists.id", ondelete="CASCADE"), nullable=True
    )  # NULL for global jobs
    status = Column(
        String(50), default="pending"
    )  # pending, running, completed, failed, retrying
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    celery_task_id = Column(String(255), nullable=True, unique=True)  # Celery task UUID
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    result_summary = Column(
        JSON, nullable=True
    )  # {"discovered": 5, "downloaded": 3, "failed": 1}
    execution_time_seconds = Column(
        Integer, nullable=True
    )  # How long the job took to execute
    triggered_by = Column(
        String(50), default="scheduler"
    )  # 'scheduler', 'manual', 'api', 'webhook'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    artist = relationship("Artist", backref="scheduled_jobs")

    # Indexes
    __table_args__ = (
        Index("idx_scheduled_job_type", "job_type"),
        Index("idx_scheduled_job_status", "status"),
        Index("idx_scheduled_job_artist_id", "artist_id"),
        Index("idx_scheduled_job_celery_task_id", "celery_task_id"),
        Index("idx_scheduled_job_created_at", "created_at"),
        Index("idx_scheduled_job_started_at", "started_at"),
        Index(
            "idx_scheduled_job_type_status", "job_type", "status"
        ),  # Composite for queries
        Index(
            "idx_scheduled_job_artist_status", "artist_id", "status"
        ),  # Per-artist job status
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<ScheduledJob(id={self.id}, type='{self.job_type}', status='{self.status}', artist_id={self.artist_id})>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "job_type": self.job_type,
            "artist_id": self.artist_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "celery_task_id": self.celery_task_id,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "result_summary": self.result_summary,
            "execution_time_seconds": self.execution_time_seconds,
            "triggered_by": self.triggered_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PlaylistMonitor(Base):
    """YouTube playlist monitoring"""

    __tablename__ = "playlist_monitors"

    id = Column(Integer, primary_key=True)
    playlist_id = Column(
        String(100), unique=True, nullable=False
    )  # YouTube playlist ID
    playlist_url = Column(String(500), nullable=False)  # Original playlist URL
    name = Column(String(255), nullable=False)  # Display name for the playlist
    channel_title = Column(String(255), nullable=True)  # Channel that owns the playlist
    channel_id = Column(String(100), nullable=True)  # YouTube channel ID
    auto_download = Column(Boolean, default=True)  # Auto-download new videos
    quality = Column(String(50), default="1080p")  # Download quality preference
    keywords = Column(JSON, nullable=True)  # Keywords to filter videos
    last_check = Column(DateTime, nullable=True)  # Last time playlist was checked
    last_video_count = Column(Integer, default=0)  # Track video count changes
    last_known_video_id = Column(
        String(20), nullable=True
    )  # Last known video ID for incremental sync (YouTube quota optimization)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_playlist_id", "playlist_id"),
        Index("idx_playlist_channel_id", "channel_id"),
        Index("idx_playlist_auto_download", "auto_download"),
        Index("idx_playlist_last_check", "last_check"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return (
            f"<PlaylistMonitor(name='{self.name}', playlist_id='{self.playlist_id}')>"
        )


class CustomTheme(Base):
    """Custom theme model for theme customization"""

    __tablename__ = "custom_themes"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    is_built_in = Column(Boolean, default=False, nullable=False)

    # Theme definition stored as JSON with CSS variables
    theme_data = Column(JSON, nullable=False)
    # Light theme variant (optional - falls back to theme_data if not provided)
    light_theme_data = Column(JSON, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = relationship("User", backref="created_themes")

    __table_args__ = (
        Index("idx_custom_theme_name", "name"),
        Index("idx_custom_theme_creator", "created_by"),
        Index("idx_custom_theme_public", "is_public"),
        {"extend_existing": True},
    )

    def to_dict(self):
        """Convert to dictionary for API responses"""
        result = {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "created_by": self.created_by,
            "creator_username": self.creator.username if self.creator else None,
            "is_public": self.is_public,
            "is_built_in": self.is_built_in,
            "theme_data": self.theme_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        # Handle light_theme_data gracefully in case column doesn't exist yet
        try:
            result["light_theme_data"] = self.light_theme_data
        except AttributeError:
            result["light_theme_data"] = None

        return result

    def __repr__(self):
        return f"<CustomTheme(name='{self.name}', display_name='{self.display_name}')>"


class Playlist(Base):
    """User-created playlists for organizing videos"""

    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)
    is_featured = Column(Boolean, default=False, nullable=False)  # Featured playlists
    total_duration = Column(Integer, nullable=True)  # Total duration in seconds
    video_count = Column(Integer, default=0, nullable=False)  # Cached video count
    playlist_metadata = Column(JSON, nullable=True)  # Additional metadata
    thumbnail_url = Column(String(500), nullable=True)  # Playlist thumbnail URL
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Dynamic playlist fields
    playlist_type = Column(
        SQLEnum(PlaylistType), default=PlaylistType.STATIC, nullable=False
    )
    filter_criteria = Column(
        JSON, nullable=True
    )  # Filter criteria for dynamic playlists
    auto_update = Column(
        Boolean, default=True, nullable=False
    )  # Whether to auto-update dynamic playlists
    last_updated = Column(
        DateTime, nullable=True
    )  # Last time dynamic playlist was updated

    # Relationships
    user = relationship("User", backref="playlists")
    entries = relationship(
        "PlaylistEntry",
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistEntry.position",
    )

    # Indexes
    __table_args__ = (
        Index("idx_playlist_user_id", "user_id"),
        Index("idx_playlist_name", "name"),
        Index("idx_playlist_is_public", "is_public"),
        Index("idx_playlist_is_featured", "is_featured"),
        Index("idx_playlist_created_at", "created_at"),
        Index("idx_playlist_type", "playlist_type"),  # Dynamic playlist queries
        Index("idx_playlist_auto_update", "auto_update"),  # For update jobs
        Index("idx_playlist_last_updated", "last_updated"),  # For staleness checks
        Index(
            "idx_playlist_user_public", "user_id", "is_public"
        ),  # Composite for permissions
        Index(
            "idx_playlist_type_auto", "playlist_type", "auto_update"
        ),  # For dynamic update queries
        {"extend_existing": True},
    )

    def update_stats(self):
        """Update cached statistics (video_count, total_duration)"""
        from sqlalchemy import func
        from sqlalchemy.orm import object_session

        session = object_session(self)
        if not session:
            # Fallback to relationship-based calculation if no session
            if self.entries:
                self.video_count = len(self.entries)
                total_seconds = 0
                for entry in self.entries:
                    if entry.video and entry.video.duration:
                        total_seconds += entry.video.duration
                self.total_duration = total_seconds if total_seconds > 0 else None
            else:
                self.video_count = 0
                self.total_duration = None
            return

        # Query database directly for accurate count (fixes issue #177)
        entry_count = (
            session.query(func.count(PlaylistEntry.id))
            .filter(PlaylistEntry.playlist_id == self.id)
            .scalar()
        )

        # Calculate total duration from database
        total_duration = (
            session.query(func.sum(Video.duration))
            .join(PlaylistEntry, PlaylistEntry.video_id == Video.id)
            .filter(PlaylistEntry.playlist_id == self.id)
            .scalar()
        )

        self.video_count = entry_count or 0
        self.total_duration = int(total_duration) if total_duration else None

    def can_access(self, user):
        """Check if user can access this playlist"""
        if not user:
            return self.is_public
        return self.user_id == user.id or self.is_public or user.can_access_admin()

    def can_modify(self, user):
        """Check if user can modify this playlist"""
        if not user:
            return False
        return self.user_id == user.id or user.can_access_admin()

    def to_dict(self, include_entries=False):
        """Convert playlist to dictionary"""
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "is_public": self.is_public,
            "is_featured": self.is_featured,
            "video_count": self.video_count,
            "total_duration": self.total_duration,
            "metadata": self.playlist_metadata or {},
            "thumbnail_url": self.thumbnail_url,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Dynamic playlist fields
            "playlist_type": self.playlist_type.value,
            "filter_criteria": self.filter_criteria,
            "auto_update": self.auto_update,
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
        }

        if include_entries and self.entries:
            data["entries"] = [entry.to_dict() for entry in self.entries]

        return data

    def is_dynamic(self):
        """Check if this is a dynamic playlist"""
        return self.playlist_type == PlaylistType.DYNAMIC

    def is_static(self):
        """Check if this is a static playlist"""
        return self.playlist_type == PlaylistType.STATIC

    def needs_update(self, max_age_hours=24):
        """Check if dynamic playlist needs updating based on age"""
        if not self.is_dynamic() or not self.auto_update:
            return False

        if not self.last_updated:
            return True  # Never been updated

        from datetime import datetime, timedelta

        max_age = timedelta(hours=max_age_hours)
        return datetime.utcnow() - self.last_updated > max_age

    def validate_filter_criteria(self):
        """Validate filter criteria structure"""
        if not self.is_dynamic():
            return True

        if not self.filter_criteria:
            return False

        # Define allowed filter keys
        allowed_keys = {
            "genres",
            "artists",
            "year_range",
            "duration_range",
            "quality",
            "status",
            "keywords",
            "directories",
        }

        # Check if all keys are allowed
        for key in self.filter_criteria.keys():
            if key not in allowed_keys:
                return False

        # Validate range structures
        if "year_range" in self.filter_criteria:
            year_range = self.filter_criteria["year_range"]
            if (
                not isinstance(year_range, dict)
                or "min" not in year_range
                or "max" not in year_range
            ):
                return False

        if "duration_range" in self.filter_criteria:
            duration_range = self.filter_criteria["duration_range"]
            if (
                not isinstance(duration_range, dict)
                or "min" not in duration_range
                or "max" not in duration_range
            ):
                return False

        return True

    def __repr__(self):
        return f"<Playlist(name='{self.name}', user_id={self.user_id}, type='{self.playlist_type.value}', videos={self.video_count})>"


class PlaylistEntry(Base):
    """Individual video entries in playlists"""

    __tablename__ = "playlist_entries"

    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    position = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)  # User notes for this playlist entry
    added_by = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # Who added the video
    added_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    playlist = relationship("Playlist", back_populates="entries")
    video = relationship("Video")
    user = relationship("User", backref="playlist_entries")

    # Indexes
    __table_args__ = (
        Index("idx_playlist_entry_playlist", "playlist_id"),
        Index("idx_playlist_entry_video", "video_id"),
        Index("idx_playlist_entry_position", "playlist_id", "position"),
        Index("idx_playlist_entry_added_by", "added_by"),
        Index("idx_playlist_entry_added_at", "added_at"),
        # Unique constraint to prevent duplicate videos in same playlist
        Index("idx_playlist_entry_unique", "playlist_id", "video_id", unique=True),
        {"extend_existing": True},
    )

    def to_dict(self, include_video=True):
        """Convert playlist entry to dictionary"""
        data = {
            "id": self.id,
            "playlist_id": self.playlist_id,
            "video_id": self.video_id,
            "position": self.position,
            "notes": self.notes,
            "added_by": self.added_by,
            "added_by_username": self.user.username if self.user else None,
            "added_at": self.added_at.isoformat(),
        }

        if include_video and self.video:
            data["video"] = {
                "id": self.video.id,
                "title": self.video.title,
                "artist_name": self.video.artist.name if self.video.artist else None,
                "duration": self.video.duration,
                "thumbnail_url": self.video.thumbnail_url,
                "status": self.video.status.value,
                "year": self.video.year,
                "quality": self.video.quality,
                "video_metadata": self.video.video_metadata,
            }

        return data

    def __repr__(self):
        return f"<PlaylistEntry(playlist_id={self.playlist_id}, video_id={self.video_id}, position={self.position})>"


class VideoBlacklist(Base):
    """Blacklisted YouTube URLs to prevent re-download of unwanted videos"""

    __tablename__ = "video_blacklist"

    youtube_url = Column(String(500), primary_key=True)  # YouTube URL as primary key
    title = Column(String(500), nullable=True)  # Optional: video title when blacklisted
    artist_name = Column(
        String(255), nullable=True
    )  # Optional: artist name when blacklisted
    blacklisted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    blacklisted_by = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # User who blacklisted

    # Relationships
    user = relationship("User", backref="blacklisted_videos")

    # Indexes
    __table_args__ = (
        Index("idx_blacklist_url", "youtube_url"),
        Index("idx_blacklist_date", "blacklisted_at"),
        Index("idx_blacklist_user", "blacklisted_by"),
        {"extend_existing": True},
    )

    def to_dict(self):
        """Convert blacklist entry to dictionary"""
        return {
            "youtube_url": self.youtube_url,
            "title": self.title,
            "artist_name": self.artist_name,
            "blacklisted_at": self.blacklisted_at.isoformat(),
            "blacklisted_by": self.blacklisted_by,
            "blacklisted_by_username": self.user.username if self.user else None,
        }

    def __repr__(self):
        return f"<VideoBlacklist(youtube_url='{self.youtube_url}', blacklisted_at='{self.blacklisted_at}')>"


class WizardState(Base):
    """Installation wizard state tracking for first-run setup"""

    __tablename__ = "wizard_state"

    id = Column(Integer, primary_key=True)
    status = Column(
        SQLEnum(WizardStatus), default=WizardStatus.NOT_STARTED, nullable=False
    )
    current_step = Column(
        SQLEnum(WizardStep), default=WizardStep.WELCOME, nullable=False
    )

    # Step completion tracking
    welcome_completed = Column(Boolean, default=False, nullable=False)
    admin_account_completed = Column(Boolean, default=False, nullable=False)
    directories_completed = Column(Boolean, default=False, nullable=False)
    api_config_completed = Column(Boolean, default=False, nullable=False)
    video_import_completed = Column(Boolean, default=False, nullable=False)

    # Configuration data collected during wizard (stored as JSON)
    config_data = Column(
        JSON, nullable=True
    )  # Stores directory paths, API validation results, etc.

    # Import job tracking
    import_job_id = Column(String(255), nullable=True)  # Background job ID for import
    videos_imported = Column(Integer, default=0, nullable=False)
    import_errors = Column(
        JSON, nullable=True
    )  # List of errors encountered during import

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_step_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for performance
    __table_args__ = (
        Index("idx_wizard_status", "status"),
        Index("idx_wizard_current_step", "current_step"),
        {"extend_existing": True},
    )

    def is_completed(self):
        """Check if wizard is fully completed"""
        return self.status == WizardStatus.COMPLETED

    def is_in_progress(self):
        """Check if wizard is currently in progress"""
        return self.status == WizardStatus.IN_PROGRESS

    def get_completion_percentage(self):
        """Calculate wizard completion percentage based on completed steps"""
        total_steps = 5  # Excluding welcome step
        completed_steps = sum(
            [
                self.admin_account_completed,
                self.directories_completed,
                self.api_config_completed,
                self.video_import_completed,
                self.status == WizardStatus.COMPLETED,
            ]
        )
        return int((completed_steps / total_steps) * 100)

    def mark_step_complete(self, step: WizardStep):
        """Mark a specific step as completed"""
        step_mapping = {
            WizardStep.WELCOME: "welcome_completed",
            WizardStep.ADMIN_ACCOUNT: "admin_account_completed",
            WizardStep.DIRECTORIES: "directories_completed",
            WizardStep.API_CONFIG: "api_config_completed",
            WizardStep.VIDEO_IMPORT: "video_import_completed",
        }

        if step in step_mapping:
            setattr(self, step_mapping[step], True)
            self.last_step_at = datetime.utcnow()

        # If all steps are complete, mark wizard as completed
        if step == WizardStep.COMPLETE or (
            self.admin_account_completed
            and self.directories_completed
            and self.api_config_completed
            and self.video_import_completed
        ):
            self.status = WizardStatus.COMPLETED
            self.completed_at = datetime.utcnow()
            self.current_step = WizardStep.COMPLETE

    def advance_to_step(self, step: WizardStep):
        """Advance wizard to the next step"""
        self.current_step = step
        self.last_step_at = datetime.utcnow()

        # Mark wizard as in progress if not already
        if self.status == WizardStatus.NOT_STARTED:
            self.status = WizardStatus.IN_PROGRESS
            self.started_at = datetime.utcnow()

    def to_dict(self):
        """Convert wizard state to dictionary"""
        return {
            "id": self.id,
            "status": self.status.value,
            "current_step": self.current_step.value,
            "completion_percentage": self.get_completion_percentage(),
            "steps": {
                "welcome": self.welcome_completed,
                "admin_account": self.admin_account_completed,
                "directories": self.directories_completed,
                "api_config": self.api_config_completed,
                "video_import": self.video_import_completed,
            },
            "config_data": self.config_data or {},
            "import_job_id": self.import_job_id,
            "videos_imported": self.videos_imported,
            "import_errors": self.import_errors or [],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "last_step_at": (
                self.last_step_at.isoformat() if self.last_step_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<WizardState(id={self.id}, status='{self.status.value}', current_step='{self.current_step.value}', completion={self.get_completion_percentage()}%)>"
