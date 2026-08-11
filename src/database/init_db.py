"""
Database initialization and migration utilities
"""

from sqlalchemy import text

from src.database.connection import Base
from src.database.models import CustomTheme, Setting, User, WizardState
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
            "true",
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
            "50",
            "Maximum videos to download per scheduled run",
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
        # Scheduler V2 settings (v0.10.1)
        (
            "scheduler_v2_enabled",
            "true",
            "Enable Scheduler V2 with Celery Beat for production-grade scheduling",
        ),
        (
            "scheduler_v2_worker_count",
            "3",
            "Number of Celery workers for scheduler tasks",
        ),
        (
            "scheduler_v2_health_check_enabled",
            "true",
            "Enable periodic health checks for scheduler system",
        ),
        (
            "scheduler_v2_health_check_interval",
            "300",
            "Health check interval in seconds (default: 5 minutes)",
        ),
        (
            "discovery_parallel_workers",
            "5",
            "Number of parallel workers for video discovery tasks",
        ),
        (
            "discovery_url_resolution_timeout",
            "30",
            "Timeout for URL resolution during discovery (seconds)",
        ),
        (
            "discovery_batch_size",
            "10",
            "Number of artists to process in parallel during discovery",
        ),
        (
            "download_max_concurrent",
            "3",
            "Maximum number of concurrent video downloads",
        ),
        (
            "download_retry_max_attempts",
            "3",
            "Maximum retry attempts for failed downloads",
        ),
        (
            "download_retry_backoff_base",
            "300",
            "Base retry backoff interval in seconds (5 minutes, exponential)",
        ),
        (
            "download_priority_enabled",
            "true",
            "Enable priority-based download ordering (high/medium/low)",
        ),
        (
            "monitoring_job_retention_days",
            "30",
            "Number of days to retain scheduled job history",
        ),
        (
            "monitoring_alert_on_failure",
            "true",
            "Send alerts when scheduled jobs fail",
        ),
        (
            "monitoring_alert_threshold",
            "3",
            "Number of consecutive failures before alerting",
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
    import bcrypt

    from src.database.connection import get_db

    try:
        with get_db() as session:
            username_setting = (
                session.query(Setting).filter_by(key="simple_auth_username").first()
            )
            password_setting = (
                session.query(Setting).filter_by(key="simple_auth_password").first()
            )

            credentials_missing = not username_setting or not password_setting

            if credentials_missing or force_reset:
                if force_reset:
                    logger.info("Force resetting authentication credentials...")
                else:
                    logger.info(
                        "Default authentication credentials missing, creating..."
                    )

                default_username = "admin"
                default_password = "mvidarr"
                password_hash = bcrypt.hashpw(
                    default_password.encode(), bcrypt.gensalt()
                ).decode()

                if not username_setting:
                    username_setting = Setting(
                        key="simple_auth_username",
                        value=default_username,
                        description="Default authentication username",
                    )
                    session.add(username_setting)
                else:
                    username_setting.value = default_username

                if not password_setting:
                    password_setting = Setting(
                        key="simple_auth_password",
                        value=password_hash,
                        description="Default authentication password hash (bcrypt)",
                    )
                    session.add(password_setting)
                else:
                    password_setting.value = password_hash

                session.commit()
                logger.info(
                    f"Default credentials {'reset' if force_reset else 'created'}"
                )
            else:
                logger.info("Default authentication credentials already exist")

            configured_username = username_setting.value

        # Reconcile the Settings-table credential with a matching User row so
        # that SessionStore.create_session can resolve a real ADMIN role for it
        # instead of failing closed to READONLY.
        ensure_admin_user_for_credentials(configured_username)

        return True

    except Exception as e:
        logger.error(f"Failed to ensure default credentials: {e}")
        return False


def is_wizard_setup_pending():
    """
    Check whether the installation wizard still owns first-run setup.

    Mirrors FirstRunDetectionMiddleware._check_wizard_completed() exactly: a
    missing WizardState row, or one that is NOT_STARTED/IN_PROGRESS, means the
    whole application is locked to /wizard and the wizard is the component
    responsible for creating the first admin User. COMPLETED or SKIPPED means
    first-run setup is over and the install is live.

    On any error this returns True (pending), which is the safe direction:
    skipping reconciliation on a live install costs at worst a READONLY session
    that a later boot fixes, whereas pre-seeding an admin row on a fresh install
    permanently blocks the wizard's create-account step.

    Returns:
        True if the wizard has not yet been completed or skipped
    """
    from src.database.connection import get_db
    from src.database.models import WizardStatus

    try:
        with get_db() as session:
            wizard_state = session.query(WizardState).first()

            if wizard_state is None:
                # No row at all: the wizard has never been opened, and the
                # first-run middleware is redirecting every request to /wizard.
                return True

            return wizard_state.status not in (
                WizardStatus.COMPLETED,
                WizardStatus.SKIPPED,
            )

    except Exception as e:
        logger.warning(
            f"Could not determine installation wizard state ({e}); "
            f"assuming first-run setup is still pending"
        )
        return True


def ensure_admin_user_for_credentials(username):
    """
    Ensure a User row with ADMIN role exists for the configured
    simple_auth_username.

    SessionStore.create_session looks the username up in the users table to
    resolve the session role and fails closed to READONLY when no row exists.
    Installs that finished (or skipped) the wizard before this reconciliation
    existed only have Setting rows, so their sole admin account would get a
    READONLY session. This reconciles that.

    Deliberately a no-op while the installation wizard is still pending: on a
    fresh install the wizard's POST /api/wizard/create-admin rejects setup with
    "Admin user already exists" if any ADMIN User row is present, so seeding one
    at boot would permanently break first-run setup. Until the wizard is
    completed or skipped, the first-run middleware locks the app to /wizard
    anyway, so no session role can be needed yet. The wizard creates the real
    admin row itself on completion, and skip_wizard() calls back into this
    function so a skipped install is reconciled immediately rather than on the
    next boot.

    The User row's own password_hash is a random, unusable value: real
    authentication for this account goes through SimpleAuthService against the
    Settings table, never through User.check_password.

    Idempotent: safe to run on every boot. Never modifies an existing row.

    Returns:
        True if a matching ADMIN user exists (or was created), False on error
        or when reconciliation was skipped because the wizard is still pending
    """
    import secrets

    from src.database.connection import get_db
    from src.database.models import UserRole

    if not username:
        logger.warning(
            "No simple_auth_username configured; skipping user reconciliation"
        )
        return False

    if is_wizard_setup_pending():
        logger.info(
            "Installation wizard has not been completed or skipped; leaving "
            "admin user creation to the wizard"
        )
        return False

    try:
        with get_db() as session:
            existing = session.query(User).filter(User.username == username).first()

            if existing is not None:
                if existing.role != UserRole.ADMIN:
                    # Leave it alone: an operator may have deliberately
                    # downgraded this account. Warn loudly instead.
                    logger.warning(
                        f"User '{username}' exists with role "
                        f"{existing.role.value}, not ADMIN. Leaving it "
                        f"untouched; admin-only endpoints will 403 for it."
                    )
                else:
                    logger.debug(f"Admin user row for '{username}' already exists")
                return True

            # Random unusable password; complexity suffix satisfies
            # PasswordValidator's length/character-class rules so User()
            # does not raise. token_urlsafe's own random output occasionally
            # trips PasswordValidator's sequential- or repeated-character
            # checks by chance (e.g. contains "abc" or "123"), so retry with
            # a fresh draw on the rare occasions that happens rather than
            # trying to construct one immune to rules this function doesn't
            # own the definition of. A handful of attempts is enough that
            # exhausting them all is not a realistic outcome.
            from src.utils.security import PasswordValidator

            for _ in range(10):
                candidate = secrets.token_urlsafe(32) + "aA1!"
                if PasswordValidator.validate_password_strength(candidate)[0]:
                    placeholder_password = candidate
                    break
            else:
                logger.error(
                    f"Could not generate a placeholder password for '{username}' "
                    "that passes strength validation after 10 attempts"
                )
                return False

            user = User(
                username=username,
                email=f"{username}@localhost",
                password=placeholder_password,
                role=UserRole.ADMIN,
            )
            session.add(user)
            session.commit()
            logger.info(
                f"Created ADMIN user row for configured credential '{username}' "
                f"(authentication still goes through SimpleAuthService)"
            )
            return True

    except Exception as e:
        logger.error(f"Failed to reconcile admin user for '{username}': {e}")
        return False


def create_admin_user():
    """
    DEPRECATED: Admin user creation is now handled by the Installation Wizard (v1.0.0)

    This function is kept for backwards compatibility but is no longer called
    during database initialization. Admin users are created through the wizard UI.
    """
    logger.warning(
        "create_admin_user() is deprecated - admin creation handled by Installation Wizard"
    )
    return True  # Return True to avoid breaking old code that might call this


def init_built_in_themes():
    """Initialize built-in themes in the database

    Note: This function is primarily for backward compatibility.
    Built-in themes are now seeded via migration 015_seed_built_in_themes.py
    which runs automatically during database initialization.

    This function serves as a safety check to ensure themes exist,
    but the actual seeding is handled by the migration system.
    """
    from src.database.connection import get_db

    try:
        with get_db() as session:
            # Check if built-in themes already exist
            existing_builtin_count = (
                session.query(CustomTheme).filter_by(is_built_in=True).count()
            )

            if existing_builtin_count > 0:
                logger.info(
                    f"Built-in themes already exist ({existing_builtin_count} entries)"
                )
                return True

            # No built-in themes found - log a warning
            # Migration 015 should have created them, so this shouldn't happen
            logger.warning(
                "No built-in themes found! Migration 015 should have seeded them. "
                "Run migrations/015_seed_built_in_themes.py manually if needed."
            )

            # Don't fail initialization - themes can be added later
            return True

        return True

    except Exception as e:
        logger.error(f"Failed to check built-in themes: {e}")
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

    # NOTE: Admin user creation is now handled by the Installation Wizard (v1.0.0)
    # We no longer auto-create a default admin user during database initialization.
    # Users will create their first admin account through the wizard UI.
    logger.info("Skipping default admin user creation - handled by Installation Wizard")

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

    # Ensure built-in themes exist (failsafe check after migrations)
    # This ensures themes are seeded even if migration 015 had issues
    try:
        from src.database.ensure_themes import ensure_builtin_themes_exist

        success, count, message = ensure_builtin_themes_exist()
        if success:
            if count > 0:
                logger.info(f"Seeded {count} built-in themes")
            else:
                logger.info("Built-in themes already exist")
        else:
            logger.warning(f"Theme seeding check failed: {message}")
            # Don't fail initialization - themes can be added manually later
    except Exception as e:
        logger.warning(f"Failed to run theme seeding check: {e}")
        # Don't fail initialization - themes can be added manually later

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
