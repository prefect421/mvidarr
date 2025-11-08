"""
Configuration Management for MVidarr
"""

import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    """Application configuration"""

    # Base paths
    BASE_DIR = Path(__file__).parent.parent.parent

    # Load environment variables from .env file
    @classmethod
    def load_env(cls):
        """Load environment variables from .env file"""
        env_file = cls.BASE_DIR / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        else:
            # In Docker environments, skip .env file creation if env vars are already set
            if os.environ.get("DB_HOST") or os.environ.get("SECRET_KEY"):
                # Environment variables are already set (likely from Docker), skip .env creation
                return
            # Create default .env if it doesn't exist and we're not in Docker
            try:
                cls.create_default_env()
                load_dotenv(env_file)
            except PermissionError:
                # Skip .env file creation if we don't have write permissions (Docker environment)
                pass

    @classmethod
    def create_default_env(cls):
        """Create default .env file"""
        env_content = """# MVidarr Configuration

# Database configuration
DB_HOST=localhost
DB_PORT=3306
DB_NAME=mvidarr
DB_USER=mvidarr
DB_PASSWORD=change_me_to_your_password

# Application settings
PORT=5000
DEBUG=false
SECRET_KEY=change_me_to_random_string_for_production

# External services
IMVDB_API_KEY=
YOUTUBE_API_KEY=
METUBE_HOST=localhost
METUBE_PORT=8081

# Logging
LOG_LEVEL=INFO
LOG_MAX_SIZE=10485760
LOG_BACKUP_COUNT=5

# Database connection pooling
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
"""
        env_file = cls.BASE_DIR / ".env"
        with open(env_file, "w") as f:
            f.write(env_content)

    DATA_DIR = BASE_DIR / "data"
    LOGS_DIR = DATA_DIR / "logs"
    DOWNLOADS_DIR = DATA_DIR / "downloads"
    MUSIC_VIDEOS_DIR = DATA_DIR / "musicvideos"  # Match Docker mount path
    THUMBNAILS_DIR = DATA_DIR / "thumbnails"
    CACHE_DIR = DATA_DIR / "cache"
    BACKUPS_DIR = DATA_DIR / "backups"

    def _load_db_settings(self):
        """Load configuration from database settings"""
        try:
            from src.services.settings_service import SettingsService

            # Flask configuration
            self.SECRET_KEY = SettingsService.get(
                "secret_key", "mvidarr-dev-key-change-in-production"
            )
            self.DEBUG = SettingsService.get_bool("debug_mode", False)

            # Default application settings
            self.HOST = SettingsService.get("app_host", "0.0.0.0")
            self.PORT = SettingsService.get_int("app_port", 5000)

            # Database configuration
            self.DB_HOST = SettingsService.get("db_host", "localhost")
            self.DB_PORT = SettingsService.get_int("db_port", 3306)
            self.DB_NAME = SettingsService.get("db_name", "mvidarr")
            self.DB_USER = SettingsService.get("db_user", "mvidarr")
            self.DB_PASSWORD = SettingsService.get("db_password", "mvidarr")

            # Connection pooling
            self.DB_POOL_SIZE = SettingsService.get_int("db_pool_size", 10)
            self.DB_MAX_OVERFLOW = SettingsService.get_int("db_max_overflow", 20)
            self.DB_POOL_TIMEOUT = SettingsService.get_int("db_pool_timeout", 30)

            # External service defaults
            self.IMVDB_API_URL = "https://imvdb.com/api/v1"
            self.IMVDB_API_KEY = SettingsService.get("imvdb_api_key", "")

            self.METUBE_HOST = SettingsService.get("metube_host", "localhost")
            self.METUBE_PORT = SettingsService.get_int("metube_port", 8081)

            # YouTube API (optional)
            self.YOUTUBE_API_KEY = SettingsService.get("youtube_api_key", "")

            # Logging configuration
            self.LOG_LEVEL = SettingsService.get("log_level", "INFO")
            self.LOG_FILE = self.LOGS_DIR / "mvidarr.log"
            self.LOG_MAX_SIZE = SettingsService.get_int(
                "log_max_size", 10485760
            )  # 10MB
            self.LOG_BACKUP_COUNT = SettingsService.get_int("log_backup_count", 5)

        except Exception as e:
            # Fallback to environment variables if database is not available
            self._load_env_vars()

    def _load_env_vars(self):
        """Fallback: Load environment variables when database is not available"""
        # Flask configuration
        self.SECRET_KEY = (
            os.environ.get("SECRET_KEY") or "mvidarr-dev-key-change-in-production"
        )
        self.DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

        # Default application settings
        self.HOST = os.environ.get("HOST", "0.0.0.0")
        self.PORT = int(os.environ.get("PORT", 5000))

        # Database configuration
        self.DB_HOST = os.environ.get("DB_HOST", "localhost")
        self.DB_PORT = int(os.environ.get("DB_PORT", 3306))
        self.DB_NAME = os.environ.get("DB_NAME", "mvidarr")
        self.DB_USER = os.environ.get("DB_USER", "mvidarr")
        self.DB_PASSWORD = os.environ.get("DB_PASSWORD", "mvidarr")

        # Connection pooling
        self.DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", 10))
        self.DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", 20))
        self.DB_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", 30))

        # External service defaults
        self.IMVDB_API_URL = "https://imvdb.com/api/v1"
        self.IMVDB_API_KEY = os.environ.get("IMVDB_API_KEY", "")

        self.METUBE_HOST = os.environ.get("METUBE_HOST", "localhost")
        self.METUBE_PORT = int(os.environ.get("METUBE_PORT", 8081))

        # YouTube API (optional)
        self.YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

        # Logging configuration
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
        self.LOG_FILE = self.LOGS_DIR / "mvidarr.log"
        self.LOG_MAX_SIZE = int(os.environ.get("LOG_MAX_SIZE", 10485760))  # 10MB
        self.LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", 5))

    # Ensure directories exist
    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        for directory in [
            cls.DATA_DIR,
            cls.LOGS_DIR,
            cls.DOWNLOADS_DIR,
            cls.MUSIC_VIDEOS_DIR,
            cls.THUMBNAILS_DIR,
            cls.CACHE_DIR,
            cls.BACKUPS_DIR,
        ]:
            directory.mkdir(parents=True, exist_ok=True, mode=0o755)

    def __init__(self):
        """Initialize configuration and create directories"""
        # Load environment variables first (as fallback)
        self.load_env()
        # Load from environment variables initially
        self._load_env_vars()
        # Then create directories
        self.ensure_directories()

    def load_from_database(self):
        """Load configuration from database after initialization"""
        try:
            self._load_db_settings()
            return True
        except Exception:
            return False

    def to_dict(self):
        """Convert configuration to dictionary for Flask app.config"""
        return {
            "SECRET_KEY": getattr(self, "SECRET_KEY", "dev-key"),
            "DEBUG": getattr(self, "DEBUG", False),
            "HOST": getattr(self, "HOST", "127.0.0.1"),
            "PORT": getattr(self, "PORT", 5000),
            "DB_HOST": getattr(self, "DB_HOST", "localhost"),
            "DB_PORT": getattr(self, "DB_PORT", 3306),
            "DB_NAME": getattr(self, "DB_NAME", "mvidarr"),
            "DB_USER": getattr(self, "DB_USER", "mvidarr"),
            "DB_PASSWORD": getattr(self, "DB_PASSWORD", "mvidarr"),
            "DB_POOL_SIZE": getattr(self, "DB_POOL_SIZE", 10),
            "DB_MAX_OVERFLOW": getattr(self, "DB_MAX_OVERFLOW", 20),
            "DB_POOL_TIMEOUT": getattr(self, "DB_POOL_TIMEOUT", 30),
        }
