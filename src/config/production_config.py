"""
Production Configuration Management for MVidarr
Environment-based configuration with validation and security features
"""

import os
import secrets
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Deployment environments"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Logging levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DatabaseConfig(BaseModel):
    """Database configuration with validation"""
    host: str = Field(..., description="Database host")
    port: int = Field(3306, ge=1, le=65535, description="Database port")
    name: str = Field(..., description="Database name")
    user: str = Field(..., description="Database user")
    password: str = Field(..., description="Database password")
    pool_size: int = Field(10, ge=1, le=100, description="Connection pool size")
    max_overflow: int = Field(20, ge=0, le=200, description="Max overflow connections")
    pool_timeout: int = Field(30, ge=1, le=300, description="Pool timeout in seconds")
    pool_recycle: int = Field(3600, ge=300, description="Pool recycle time in seconds")
    
    @validator('password')
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Database password must be at least 8 characters')
        return v


class RedisConfig(BaseModel):
    """Redis configuration for caching and job queue"""
    url: Optional[str] = Field(None, description="Redis URL (redis://...)")
    host: str = Field("localhost", description="Redis host")
    port: int = Field(6379, ge=1, le=65535, description="Redis port")
    password: Optional[str] = Field(None, description="Redis password")
    db: int = Field(0, ge=0, le=15, description="Redis database number")
    ssl: bool = Field(False, description="Use SSL/TLS")
    socket_timeout: int = Field(5, ge=1, le=60, description="Socket timeout")
    socket_connect_timeout: int = Field(5, ge=1, le=60, description="Connection timeout")
    max_connections: int = Field(50, ge=1, le=1000, description="Max connections")


class SecurityConfig(BaseModel):
    """Security configuration"""
    secret_key: str = Field(..., min_length=32, description="Application secret key")
    session_lifetime: int = Field(86400, ge=300, description="Session lifetime in seconds")
    password_min_length: int = Field(8, ge=8, le=128, description="Minimum password length")
    max_login_attempts: int = Field(5, ge=1, le=20, description="Max login attempts")
    lockout_duration: int = Field(900, ge=60, description="Account lockout duration")
    csrf_protection: bool = Field(True, description="Enable CSRF protection")
    secure_cookies: bool = Field(True, description="Use secure cookies in production")
    
    @validator('secret_key')
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError('Secret key must be at least 32 characters')
        return v


class StorageConfig(BaseModel):
    """Storage configuration for videos and metadata"""
    video_directory: Path = Field(..., description="Video storage directory")
    thumbnail_directory: Path = Field(..., description="Thumbnail storage directory")
    backup_directory: Optional[Path] = Field(None, description="Backup storage directory")
    max_video_size: int = Field(5368709120, ge=1048576, description="Max video size in bytes (5GB)")
    allowed_video_formats: List[str] = Field(
        default=["mp4", "mkv", "webm", "avi", "mov"], 
        description="Allowed video formats"
    )
    cleanup_temp_files: bool = Field(True, description="Auto-cleanup temporary files")


class PerformanceConfig(BaseModel):
    """Performance and scaling configuration"""
    worker_processes: int = Field(4, ge=1, le=32, description="Number of worker processes")
    worker_connections: int = Field(1000, ge=100, le=10000, description="Connections per worker")
    request_timeout: int = Field(30, ge=5, le=300, description="Request timeout in seconds")
    keepalive_timeout: int = Field(5, ge=1, le=60, description="Keep-alive timeout")
    max_request_size: int = Field(104857600, ge=1048576, description="Max request size (100MB)")
    enable_gzip: bool = Field(True, description="Enable GZIP compression")
    cache_ttl: int = Field(300, ge=0, description="Default cache TTL in seconds")


class MonitoringConfig(BaseModel):
    """Monitoring and observability configuration"""
    enable_metrics: bool = Field(True, description="Enable metrics collection")
    metrics_port: int = Field(9090, ge=1024, le=65535, description="Metrics server port")
    health_check_interval: int = Field(30, ge=5, le=300, description="Health check interval")
    log_level: LogLevel = Field(LogLevel.INFO, description="Logging level")
    log_format: str = Field("json", description="Log format (json/text)")
    enable_profiling: bool = Field(False, description="Enable application profiling")
    sentry_dsn: Optional[str] = Field(None, description="Sentry DSN for error tracking")


class IntegrationConfig(BaseModel):
    """External service integration configuration"""
    spotify_client_id: Optional[str] = Field(None, description="Spotify API client ID")
    spotify_client_secret: Optional[str] = Field(None, description="Spotify API client secret")
    youtube_api_key: Optional[str] = Field(None, description="YouTube API key")
    imvdb_api_key: Optional[str] = Field(None, description="IMVDb API key")
    lastfm_api_key: Optional[str] = Field(None, description="Last.fm API key")
    metube_url: Optional[str] = Field(None, description="MeTube instance URL")
    plex_server_url: Optional[str] = Field(None, description="Plex server URL")
    plex_token: Optional[str] = Field(None, description="Plex authentication token")


class ProductionSettings(BaseSettings):
    """Complete production configuration with environment-based loading"""
    
    # Environment settings
    environment: Environment = Field(Environment.DEVELOPMENT, description="Deployment environment")
    debug: bool = Field(False, description="Debug mode")
    testing: bool = Field(False, description="Testing mode")
    
    # Application settings
    app_name: str = Field("MVidarr", description="Application name")
    app_version: str = Field("0.9.8", description="Application version")
    app_host: str = Field("0.0.0.0", description="Application host")
    app_port: int = Field(5000, ge=1024, le=65535, description="Application port")
    
    # Database configuration
    database: DatabaseConfig = Field(..., description="Database configuration")
    
    # Redis configuration
    redis: Optional[RedisConfig] = Field(None, description="Redis configuration")
    
    # Security configuration
    security: SecurityConfig = Field(..., description="Security configuration")
    
    # Storage configuration
    storage: StorageConfig = Field(..., description="Storage configuration")
    
    # Performance configuration
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig, description="Performance configuration")
    
    # Monitoring configuration
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig, description="Monitoring configuration")
    
    # Integration configuration
    integrations: IntegrationConfig = Field(default_factory=IntegrationConfig, description="Integration configuration")
    
    # Feature flags
    feature_flags: Dict[str, bool] = Field(
        default_factory=lambda: {
            "enable_background_jobs": True,
            "enable_websocket_progress": True,
            "enable_video_streaming": True,
            "enable_thumbnail_generation": True,
            "enable_metadata_enrichment": True,
            "enable_spotify_integration": False,
            "enable_youtube_integration": True,
            "enable_plex_integration": False,
            "enable_lidarr_integration": False,
        },
        description="Feature toggle flags"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
        case_sensitive = False
        
        # Environment variable mappings
        fields = {
            "app_host": {"env": "MVIDARR_HOST"},
            "app_port": {"env": "MVIDARR_PORT"},
            "database": {"env": "MVIDARR_DATABASE"},
            "redis": {"env": "MVIDARR_REDIS"},
            "security": {"env": "MVIDARR_SECURITY"},
        }
    
    @validator('environment')
    def validate_environment_specific_settings(cls, v, values):
        """Validate environment-specific requirements"""
        if v == Environment.PRODUCTION:
            # Production-specific validations
            if values.get('debug', False):
                raise ValueError('Debug mode must be disabled in production')
                
            security_config = values.get('security')
            if security_config and not security_config.secure_cookies:
                raise ValueError('Secure cookies must be enabled in production')
                
        return v
    
    @validator('database')
    def validate_database_production_settings(cls, v, values):
        """Validate database settings for production"""
        env = values.get('environment', Environment.DEVELOPMENT)
        
        if env == Environment.PRODUCTION:
            if v.pool_size < 5:
                raise ValueError('Production database pool size should be at least 5')
            if v.max_overflow < 10:
                raise ValueError('Production database max overflow should be at least 10')
                
        return v
    
    def generate_secure_secret_key(self) -> str:
        """Generate a cryptographically secure secret key"""
        return secrets.token_urlsafe(32)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary, masking sensitive values"""
        config_dict = self.dict()
        
        # Mask sensitive values
        if 'database' in config_dict and 'password' in config_dict['database']:
            config_dict['database']['password'] = '*' * 8
            
        if 'security' in config_dict and 'secret_key' in config_dict['security']:
            config_dict['security']['secret_key'] = '*' * 16
            
        # Mask API keys and tokens
        if 'integrations' in config_dict:
            for key in config_dict['integrations']:
                if key.endswith('_secret') or key.endswith('_key') or key.endswith('_token'):
                    if config_dict['integrations'][key]:
                        config_dict['integrations'][key] = '*' * 8
                        
        return config_dict
    
    def validate_production_readiness(self) -> List[str]:
        """Validate configuration for production readiness"""
        issues = []
        
        if self.environment == Environment.PRODUCTION:
            # Check critical production settings
            if self.debug:
                issues.append("Debug mode is enabled in production")
                
            if not self.security.secure_cookies:
                issues.append("Secure cookies are disabled in production")
                
            if self.security.secret_key == "change-me-in-production":
                issues.append("Default secret key is being used in production")
                
            if not self.monitoring.enable_metrics:
                issues.append("Metrics collection is disabled in production")
                
            # Check storage directories exist
            if not self.storage.video_directory.exists():
                issues.append(f"Video directory does not exist: {self.storage.video_directory}")
                
            if not self.storage.thumbnail_directory.exists():
                issues.append(f"Thumbnail directory does not exist: {self.storage.thumbnail_directory}")
                
        return issues


def load_production_config() -> ProductionSettings:
    """Load production configuration from environment"""
    try:
        # Load from environment variables and .env file
        config = ProductionSettings()
        
        # Auto-generate secret key if not provided
        if not hasattr(config.security, 'secret_key') or len(config.security.secret_key) < 32:
            config.security.secret_key = config.generate_secure_secret_key()
        
        # Validate production readiness
        if config.environment == Environment.PRODUCTION:
            issues = config.validate_production_readiness()
            if issues:
                raise ValueError(f"Production configuration issues: {'; '.join(issues)}")
        
        return config
        
    except Exception as e:
        # Fallback to development configuration
        print(f"Failed to load production config: {e}")
        print("Falling back to development configuration")
        
        return ProductionSettings(
            environment=Environment.DEVELOPMENT,
            database=DatabaseConfig(
                host=os.getenv("DB_HOST", "localhost"),
                name=os.getenv("DB_NAME", "mvidarr"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD", "password")
            ),
            security=SecurityConfig(
                secret_key=secrets.token_urlsafe(32)
            ),
            storage=StorageConfig(
                video_directory=Path("./videos"),
                thumbnail_directory=Path("./thumbnails")
            )
        )


def create_sample_env_file(filepath: str = ".env.example"):
    """Create a sample environment file with all configuration options"""
    sample_config = """
# MVidarr Production Configuration
# Copy this file to .env and customize for your environment

# Environment settings
MVIDARR_ENVIRONMENT=production
MVIDARR_DEBUG=false
MVIDARR_HOST=0.0.0.0
MVIDARR_PORT=5000

# Database configuration
MVIDARR_DATABASE__HOST=localhost
MVIDARR_DATABASE__PORT=3306
MVIDARR_DATABASE__NAME=mvidarr
MVIDARR_DATABASE__USER=mvidarr_user
MVIDARR_DATABASE__PASSWORD=your_secure_password_here
MVIDARR_DATABASE__POOL_SIZE=10
MVIDARR_DATABASE__MAX_OVERFLOW=20

# Redis configuration (optional)
MVIDARR_REDIS__URL=redis://localhost:6379/0
MVIDARR_REDIS__PASSWORD=your_redis_password

# Security configuration
MVIDARR_SECURITY__SECRET_KEY=your_32_character_secret_key_here
MVIDARR_SECURITY__SESSION_LIFETIME=86400
MVIDARR_SECURITY__SECURE_COOKIES=true

# Storage configuration
MVIDARR_STORAGE__VIDEO_DIRECTORY=/data/videos
MVIDARR_STORAGE__THUMBNAIL_DIRECTORY=/data/thumbnails
MVIDARR_STORAGE__BACKUP_DIRECTORY=/data/backups

# Performance configuration
MVIDARR_PERFORMANCE__WORKER_PROCESSES=4
MVIDARR_PERFORMANCE__WORKER_CONNECTIONS=1000

# Monitoring configuration
MVIDARR_MONITORING__LOG_LEVEL=INFO
MVIDARR_MONITORING__ENABLE_METRICS=true
MVIDARR_MONITORING__SENTRY_DSN=your_sentry_dsn_here

# Integration configuration
MVIDARR_INTEGRATIONS__SPOTIFY_CLIENT_ID=your_spotify_client_id
MVIDARR_INTEGRATIONS__SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
MVIDARR_INTEGRATIONS__YOUTUBE_API_KEY=your_youtube_api_key
MVIDARR_INTEGRATIONS__IMVDB_API_KEY=your_imvdb_api_key

# Feature flags
MVIDARR_FEATURE_FLAGS__ENABLE_SPOTIFY_INTEGRATION=false
MVIDARR_FEATURE_FLAGS__ENABLE_PLEX_INTEGRATION=false
"""
    
    with open(filepath, 'w') as f:
        f.write(sample_config.strip())
    
    print(f"Sample environment file created: {filepath}")


# Global configuration instance
production_config: Optional[ProductionSettings] = None


def get_production_config() -> ProductionSettings:
    """Get the global production configuration instance"""
    global production_config
    
    if production_config is None:
        production_config = load_production_config()
    
    return production_config