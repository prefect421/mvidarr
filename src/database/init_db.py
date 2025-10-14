"""
Database initialization and migration utilities
"""

from sqlalchemy import text

from src.database.connection import Base
from src.database.models import CustomTheme, Setting, User
from src.utils.logger import get_logger

logger = get_logger("mvidarr.database")


def create_tables():
    """Create all database tables"""
    try:
        import src.database.connection as db_conn

        if db_conn.db_manager is None:
            logger.error("Database manager not initialized")
            return False

        engine = db_conn.db_manager.create_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        return False


def init_default_settings():
    """Initialize default application settings"""
    from src.database.connection import get_db

    default_settings = [
        ("app_port", "5000", "Application port"),
        ("app_host", "0.0.0.0", "Application host"),
        ("downloads_path", "data/downloads", "Downloads directory path"),
        ("music_videos_path", "data/musicvideos", "Music videos directory path"),
        ("thumbnails_path", "data/thumbnails", "Thumbnails directory path"),
        ("metube_host", "localhost", "MeTube host"),
        ("metube_port", "8081", "MeTube port"),
        ("imvdb_api_key", "", "IMVDB API key"),
        ("youtube_api_key", "", "YouTube API key"),
        (
            "auto_organize_downloads",
            "true",
            "Automatically organize downloads by artist",
        ),
        ("video_quality_preference", "best", "Preferred video quality"),
        ("max_concurrent_downloads", "3", "Maximum concurrent downloads"),
        ("enable_notifications", "true", "Enable system notifications"),
        ("language", "en", "Application language"),
        ("debug_mode", "false", "Enable debug mode"),
        (
            "require_authentication",
            "false",
            "Require user login to access the application",
        ),
        (
            "auto_download_schedule_enabled",
            "true",
            "Enable scheduled automatic downloads",
        ),
        (
            "auto_download_schedule_time",
            "02:00",
            "Time to run automatic downloads (HH:MM format) - ignored for hourly downloads",
        ),
        (
            "auto_download_schedule_days",
            "hourly",
            "Schedule frequency: hourly, daily, weekly, or specific days (monday,tuesday,etc)",
        ),
        (
            "auto_download_max_videos",
            "10",
            "Maximum videos to download per scheduled run (optimized for hourly downloads)",
        ),
        (
            "auto_discovery_schedule_enabled",
            "true",
            "Enable scheduled automatic video discovery for monitored artists",
        ),
        (
            "auto_discovery_schedule_time",
            "06:00",
            "Time to run automatic video discovery (HH:MM format)",
        ),
        (
            "auto_discovery_schedule_days",
            "daily",
            "Discovery schedule frequency: daily, weekly, twice_daily, or specific days",
        ),
        (
            "auto_discovery_max_videos_per_artist",
            "5",
            "Maximum new videos to discover per artist per scheduled run",
        ),
        ("spotify_client_id", "", "Spotify application client ID"),
        ("spotify_client_secret", "", "Spotify application client secret"),
        (
            "spotify_redirect_uri",
            "http://127.0.0.1:5000/api/spotify/callback",
            "Spotify OAuth redirect URI",
        ),
        ("ui_theme", "default", "User interface theme selection"),
    ]

    try:
        with get_db() as session:
            # Check if settings already exist
            existing_count = session.query(Setting).count()

            if existing_count == 0:
                # Insert default settings
                for key, value, description in default_settings:
                    setting = Setting(key=key, value=value, description=description)
                    session.add(setting)

                session.commit()
                logger.info(f"Initialized {len(default_settings)} default settings")
            else:
                logger.info(f"Settings already exist ({existing_count} entries)")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize default settings: {e}")
        return False


def ensure_default_credentials(force_reset=False):
    """Ensure default authentication credentials exist in settings"""
    import hashlib

    from src.database.connection import get_db

    try:
        with get_db() as session:
            # Check if simple auth credentials exist
            username_setting = (
                session.query(Setting).filter_by(key="simple_auth_username").first()
            )
            password_setting = (
                session.query(Setting).filter_by(key="simple_auth_password").first()
            )

            credentials_missing = not username_setting or not password_setting

            if credentials_missing or force_reset:
                if force_reset:
                    logger.info(
                        "Force resetting authentication credentials to defaults..."
                    )
                else:
                    logger.info(
                        "Default authentication credentials missing, creating them..."
                    )

                # Default credentials
                default_username = "admin"
                default_password = "mvidarr"
                password_hash = hashlib.sha256(default_password.encode()).hexdigest()

                logger.info(
                    f"INIT: Creating default credentials - username='{default_username}', password='{default_password}'"
                )
                logger.info(f"INIT: Generated password hash='{password_hash}'")

                # Create or update username setting
                if not username_setting:
                    username_setting = Setting(
                        key="simple_auth_username",
                        value=default_username,
                        description="Default authentication username",
                    )
                    session.add(username_setting)
                    logger.info("Created default username setting")
                else:
                    username_setting.value = default_username
                    logger.info("Updated username setting")

                # Create or update password setting
                if not password_setting:
                    password_setting = Setting(
                        key="simple_auth_password",
                        value=password_hash,
                        description="Default authentication password hash (SHA-256)",
                    )
                    session.add(password_setting)
                    logger.info("Created default password setting")
                else:
                    password_setting.value = password_hash
                    logger.info("Updated password setting")

                session.commit()
                logger.info(
                    f"Default credentials {'reset' if force_reset else 'created'} - Username: {default_username}, Password: {default_password}"
                )
            else:
                logger.info("Default authentication credentials already exist")

        return True

    except Exception as e:
        logger.error(f"Failed to ensure default credentials: {e}")
        return False


def create_admin_user():
    """Create default admin user"""
    from src.database.connection import get_db
    from src.database.models import UserRole

    try:
        with get_db() as session:
            # Check if any users exist
            existing_users = session.query(User).count()

            if existing_users == 0:
                # Create default admin user with secure password
                # Password: MVidarr@P4ss! (meets all security requirements, avoids common patterns)
                secure_password = "MVidarr@P4ss!"
                admin_user = User(
                    username="admin",
                    email="admin@localhost",
                    password=secure_password,
                    role=UserRole.ADMIN,
                )
                session.add(admin_user)
                session.commit()

                logger.info(
                    f"Created default admin user (username: admin, password: {secure_password})"
                )
            else:
                logger.info(f"Users already exist ({existing_users} entries)")

        return True

    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")
        return False


def init_built_in_themes():
    """Initialize built-in themes in the database"""
    from src.database.connection import get_db

    try:
        with get_db() as session:
            # Get admin user for theme ownership
            admin_user = session.query(User).filter_by(username="admin").first()
            if not admin_user:
                logger.warning("Admin user not found for theme initialization")
                return True  # Don't fail initialization if admin user is missing

            # Check if built-in themes already exist
            existing_builtin_count = (
                session.query(CustomTheme).filter_by(is_built_in=True).count()
            )

            if existing_builtin_count > 0:
                logger.info(
                    f"Built-in themes already exist ({existing_builtin_count} entries)"
                )
                return True

            # Define the new built-in themes (all database themes removed)
            new_themes = []

            # Create the themes
            themes_created = 0
            for theme_data in new_themes:
                # Check if theme already exists by name
                existing_theme = (
                    session.query(CustomTheme)
                    .filter_by(name=theme_data["name"])
                    .first()
                )
                if existing_theme:
                    logger.info(
                        f"Theme '{theme_data['name']}' already exists, skipping"
                    )
                    continue

                theme = CustomTheme(
                    name=theme_data["name"],
                    display_name=theme_data["display_name"],
                    description=theme_data["description"],
                    created_by=admin_user.id,
                    is_public=True,
                    is_built_in=True,
                    theme_data=theme_data["theme_data"],
                )
                session.add(theme)
                themes_created += 1

            if themes_created > 0:
                session.commit()
                logger.info(f"Created {themes_created} built-in themes")
            else:
                logger.info("All built-in themes already exist")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize built-in themes: {e}")
        return False


def check_database_health():
    """Check database health and connectivity"""
    try:
        import src.database.connection as db_conn

        if db_conn.db_manager is None:
            logger.error("Database manager not initialized")
            return False

        engine = db_conn.db_manager.create_engine()
        with engine.connect() as connection:
            # Test basic connectivity
            result = connection.execute(text("SELECT 1"))
            if result.fetchone()[0] != 1:
                return False

            # Check if all tables exist
            tables = [
                "settings",
                "artists",
                "videos",
                "downloads",
                "users",
                "task_queue",
                "custom_themes",
            ]
            for table in tables:
                result = connection.execute(text(f"SHOW TABLES LIKE '{table}'"))
                if not result.fetchone():
                    logger.error(f"Table '{table}' does not exist")
                    return False

            logger.info("Database health check passed")
            return True

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


def initialize_database():
    """Complete database initialization"""
    logger.info("Starting database initialization...")

    # Initialize database manager first
    import src.database.connection as db_conn
    from src.config.config import Config
    from src.database.connection import DatabaseManager

    if db_conn.db_manager is None:
        config = Config()
        db_conn.db_manager = DatabaseManager(config)

        # Test connection to existing database
        if not db_conn.db_manager.test_connection():
            logger.error("Database connection test failed")
            return False

    # Create tables
    if not create_tables():
        logger.error("Failed to create database tables")
        return False

    # Initialize default settings
    if not init_default_settings():
        logger.error("Failed to initialize default settings")
        return False

    # Ensure default authentication credentials exist
    if not ensure_default_credentials():
        logger.error("Failed to ensure default credentials")
        return False

    # Create admin user
    if not create_admin_user():
        logger.error("Failed to create admin user")
        return False

    # Initialize built-in themes
    if not init_built_in_themes():
        logger.error("Failed to initialize built-in themes")
        return False

    # Run database migrations
    try:
        from src.database.migrations import run_migrations

        migration_results = run_migrations()
        if migration_results["success"]:
            if migration_results["applied_migrations"]:
                logger.info(
                    f"Applied {len(migration_results['applied_migrations'])} database migrations"
                )
            else:
                logger.info("No database migrations needed")
        else:
            logger.error(f"Database migrations failed: {migration_results['errors']}")
            return False
    except Exception as e:
        logger.error(f"Failed to run database migrations: {e}")
        return False

    # Health check
    if not check_database_health():
        logger.error("Database health check failed")
        return False

    # Create performance optimization indexes
    try:
        from src.database.performance_optimizations import DatabasePerformanceOptimizer

        optimizer = DatabasePerformanceOptimizer()
        optimizer.create_performance_indexes()
        logger.info("Performance indexes created successfully")
    except ImportError:
        logger.warning("Performance optimizer not available, skipping index creation")
    except Exception as e:
        logger.warning(f"Performance index creation failed: {e}")

    logger.info("Database initialization completed successfully")
    return True


if __name__ == "__main__":
    from src.database.connection import init_db

    class DummyApp:
        def __init__(self):
            self.config = {}

    app = DummyApp()
    init_db(app)

    if initialize_database():
        print("Database initialization successful")
    else:
        print("Database initialization failed")
        exit(1)
